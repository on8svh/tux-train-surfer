"""Game simulation: player physics, obstacles, power-ups, collisions and the track generator.

This module has no pygame dependency so it can be unit tested headless.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass

from . import config as C
from .levels import Level


def lane_x(lane: int) -> float:
    return lane * C.LANE_WIDTH


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


POWERUPS = ("magnet", "board", "jetpack", "superjump", "coffee")
DUCK_STYLES = ("squash", "roll", "belly")


# --------------------------------------------------------------------------- entities
@dataclass
class Obstacle:
    kind: str            # "train" | "ramp" | "low" (firewall) | "high" (cable) | "zombie"
    lane: int
    z: float             # near end
    length: float
    height: float
    vz: float = 0.0      # < 0: drives towards the player
    cars: int = 1
    color: int = 0
    hit: bool = False
    horn: bool = False
    passed: bool = False
    x: float = 0.0       # zombies walk sideways: current x
    vx: float = 0.0

    def __post_init__(self) -> None:
        if self.kind != "zombie":
            self.x = lane_x(self.lane)

    @property
    def z1(self) -> float:
        return self.z + self.length

    @property
    def half_width(self) -> float:
        if self.kind in ("train", "ramp"):
            return C.TRAIN_WIDTH / 2
        if self.kind == "zombie":
            return 0.45
        return C.BARRIER_WIDTH / 2

    def surface(self, z: float) -> float:
        """Walkable height at depth z (trains and ramps only)."""
        if self.kind == "train":
            return self.height
        if self.kind == "ramp":
            return clamp((z - self.z) / self.length, 0.0, 1.0) * self.height
        return 0.0


@dataclass
class Pickup:
    kind: str            # "fish" | "golden" | "key"
    x: float
    y: float
    z: float
    taken: bool = False
    attracted: bool = False


@dataclass
class PowerUp:
    kind: str            # one of POWERUPS
    x: float
    y: float
    z: float
    taken: bool = False


@dataclass
class IcePatch:
    lane: int | None     # None = all three lanes
    z: float
    length: float

    @property
    def z1(self) -> float:
        return self.z + self.length

    def covers(self, lane: int, z: float) -> bool:
        return (self.lane is None or self.lane == lane) and self.z <= z <= self.z1


class Player:
    def __init__(self) -> None:
        self.lane = 0
        self.x = 0.0
        self.y = 0.0
        self.vy = 0.0
        self.z = 0.0
        self.grounded = True
        self.duck_t = 0.0
        self.duck_style = "squash"
        self.sliding = False
        self.run_phase = 0.0
        self.stumble_anim = 0.0
        self.land_anim = 0.0
        self.super_jumping = False

    @property
    def ducking(self) -> bool:
        return self.duck_t > 0.0

    @property
    def height(self) -> float:
        return C.PLAYER_DUCK_HEIGHT if (self.ducking or self.sliding) else C.PLAYER_HEIGHT

    @property
    def lane_now(self) -> int:
        return int(clamp(round(self.x / C.LANE_WIDTH), -1, 1))


# --------------------------------------------------------------------------- world
class World:
    """One run through a level (or endless)."""

    def __init__(self, level: Level, seed: int | None = None, demo: bool = False,
                 multiplier: int = 1, chaser: str | None = None) -> None:
        self.level = level
        self.rng = random.Random(seed)
        self.demo = demo
        self.base_multiplier = max(1, multiplier)
        self.chaser = chaser or level.chaser
        if self.chaser == "random":
            self.chaser = self.rng.choice(("thief", "kernel", "segfault", "lockin"))
        self.player = Player()
        self.obstacles: list[Obstacle] = []
        self.pickups: list[Pickup] = []
        self.powerups: list[PowerUp] = []
        self.ice: list[IcePatch] = []
        self.events: list[tuple[str, object]] = []
        self.stats: Counter = Counter()
        self.time = 0.0
        self.speed = level.speed_at(0.0)
        self.score_f = 0.0
        self.fish_count = 0
        self.keys = 0
        self.stumbles = 0
        self.stumble_timer = 0.0
        self.bump_cooldown = 0.0
        self.slow_timer = 0.0
        self.thief_dist = 2.2
        # power-up timers
        self.magnet_t = 0.0
        self.coffee_t = 0.0
        self.jetpack_t = 0.0
        self.superjump_t = 0.0
        self.board = False
        self.invuln = 0.0
        self.state = "run"           # run | caught | complete
        self.end_time = 0.0
        self.cause = ""
        self.gen_z = 30.0
        self.gen_done = False
        self.reserved = {lane: 0.0 for lane in C.LANES}
        self._color_i = 0
        self._last_z = 0.0
        self._generate()

    # ------------------------------------------------------------------ helpers
    @property
    def distance(self) -> float:
        return self.player.z

    @property
    def multiplier(self) -> int:
        return self.base_multiplier * (2 if self.coffee_t > 0 else 1)

    @property
    def score(self) -> int:
        return int(self.score_f)

    @property
    def jetpacking(self) -> bool:
        return self.jetpack_t > 0

    @property
    def can_control(self) -> bool:
        return self.state == "run" and not self.player.sliding

    @property
    def theme(self):
        return self.level.theme_at(self.player.z)

    def emit(self, name: str, data: object = None) -> None:
        self.events.append((name, data))

    def pop_events(self) -> list[tuple[str, object]]:
        ev, self.events = self.events, []
        return ev

    # backwards friendly alias used by the renderer
    @property
    def fish(self):
        return self.pickups

    # ------------------------------------------------------------------ input
    def move(self, direction: int) -> None:
        if not self.can_control:
            return
        new = int(clamp(self.player.lane + direction, -1, 1))
        if new != self.player.lane:
            self.player.lane = new
            self.emit("swoosh")
        else:
            self.emit("bonk")

    def jump(self) -> None:
        p = self.player
        if not self.can_control or not p.grounded or self.jetpacking:
            return
        sj = self.superjump_t > 0
        p.vy = C.SUPER_JUMP_VELOCITY if sj else C.JUMP_VELOCITY
        p.super_jumping = sj
        p.grounded = False
        p.duck_t = 0.0
        if sj:
            self.stats["superjumps"] += 1
        self.emit("superjump" if sj else "jump")

    def duck(self) -> None:
        p = self.player
        if not self.can_control or self.jetpacking:
            return
        if not p.grounded:
            p.vy = min(p.vy, C.FAST_FALL_VELOCITY)
        p.duck_t = C.DUCK_TIME
        p.duck_style = self.rng.choice(DUCK_STYLES)
        self.emit("duck")

    # ------------------------------------------------------------------ queries
    def support_height(self, x: float, z: float, y: float) -> float:
        """Highest walkable surface under (x, z) that Tux can reach from height y."""
        h = 0.0
        for o in self.obstacles:
            if o.kind not in ("train", "ramp") or o.hit:
                continue
            if abs(x - o.x) > o.half_width + 0.15:
                continue
            if not (o.z - 0.2 <= z <= o.z1 + 0.3):
                continue
            s = o.surface(z)
            if s > h and y >= s - C.STEP_UP:
                h = s
        return h

    def ice_at(self, lane: int, z: float) -> bool:
        return any(p.covers(lane, z) for p in self.ice)

    # ------------------------------------------------------------------ update
    def update(self, dt: float) -> None:
        steps = max(1, int(math.ceil(dt / (1 / 120))))
        h = dt / steps
        for _ in range(steps):
            self._step(h)

    def _step(self, dt: float) -> None:
        p = self.player
        self.time += dt
        if self.state != "run":
            self.end_time += dt
            if self.state == "caught":
                self.thief_dist = max(0.7, self.thief_dist - dt * 6)
            else:
                self.speed = max(4.0, self.speed - dt * 10)
                p.z += self.speed * dt
                p.run_phase += dt * self.speed * 0.9
                self.thief_dist += dt * 8
                if not p.grounded:
                    p.vy -= C.GRAVITY * dt
                    p.y = max(0.0, p.y + p.vy * dt)
                    if p.y <= 0:
                        p.grounded = True
            self._move_obstacles(dt)
            return

        target_speed = self.level.speed_at(p.z)
        if self.slow_timer > 0:
            self.slow_timer -= dt
            target_speed *= 0.7
        if self.jetpacking:
            target_speed *= 1.15
        self.speed += (target_speed - self.speed) * min(1.0, dt * 3)
        p.z += self.speed * dt
        self.score_f += self.speed * dt * self.multiplier
        p.run_phase += dt * self.speed * 0.9
        self._move_obstacles(dt)

        # lateral
        tx = lane_x(p.lane)
        step = C.LANE_CHANGE_SPEED * dt
        p.x = tx if abs(tx - p.x) <= step else p.x + math.copysign(step, tx - p.x)

        # vertical
        if self.jetpacking:
            self.jetpack_t -= dt
            p.grounded = False
            p.duck_t = 0.0
            p.vy = 0.0
            p.y += (C.JETPACK_HEIGHT - p.y) * min(1.0, dt * 3)
            if self.jetpack_t <= 0:
                self.jetpack_t = 0.0
                self.invuln = max(self.invuln, 1.2)
                # sky fish that were not reached would otherwise float in the camera's face
                self.pickups = [f for f in self.pickups if f.y < C.JETPACK_HEIGHT - 1 or f.z < p.z]
                self.emit("jetpack_end")
        else:
            ground = self.support_height(p.x, p.z, p.y)
            if p.grounded:
                if ground < p.y - 0.05:
                    p.grounded = False
                    p.vy = 0.0
                else:
                    p.y = ground
            if not p.grounded:
                p.vy -= C.GRAVITY * dt
                p.y += p.vy * dt
                ground = self.support_height(p.x, p.z, p.y - p.vy * dt)
                if p.y <= ground and p.vy <= 0:
                    p.y = ground
                    p.vy = 0.0
                    p.grounded = True
                    p.super_jumping = False
                    p.land_anim = 0.18
                    self.emit("land")
            if p.grounded and p.y > 1.0:
                self.stats["roof_m"] += self.speed * dt

        if p.duck_t > 0 and p.grounded:
            p.duck_t -= dt
        p.land_anim = max(0.0, p.land_anim - dt)
        p.stumble_anim = max(0.0, p.stumble_anim - dt)

        # ice
        on_ice = p.grounded and p.y < 0.05 and self.ice_at(p.lane_now, p.z)
        if on_ice and not p.sliding:
            p.sliding = True
            p.duck_t = 0.0
            self.stats["slips"] += 1
            self.emit("slip")
        elif not on_ice and p.sliding:
            p.sliding = False

        if not self.demo:
            self._collide()
        self._count_passed()
        self._collect(dt)

        # timers
        self.magnet_t = max(0.0, self.magnet_t - dt)
        self.coffee_t = max(0.0, self.coffee_t - dt)
        self.superjump_t = max(0.0, self.superjump_t - dt)
        self.invuln = max(0.0, self.invuln - dt)
        self.bump_cooldown = max(0.0, self.bump_cooldown - dt)
        if self.stumble_timer > 0:
            self.stumble_timer = max(0.0, self.stumble_timer - dt)
        target = C.THIEF_NEAR if self.stumble_timer > 0 else C.THIEF_FAR
        rate = 5.0 if target < self.thief_dist else 2.5
        self.thief_dist += clamp(target - self.thief_dist, -rate * dt, rate * dt)

        for o in self.obstacles:
            if o.vz < 0 and not o.horn and o.z - p.z < 95:
                o.horn = True
                self.emit("horn", o.lane)

        self.stats["distance"] = int(p.z)
        if not self.level.endless and p.z >= self.level.length and self.state == "run":
            self.state = "complete"
            self.end_time = 0.0
            self.jetpack_t = 0.0
            self.emit("complete")

        self._generate()
        self._cleanup()

    def _move_obstacles(self, dt: float) -> None:
        for o in self.obstacles:
            if o.vz:
                o.z += o.vz * dt
            if o.kind == "zombie" and not o.hit:
                o.x += o.vx * dt
                lim = C.LANE_WIDTH * 1.25
                if abs(o.x) > lim:
                    o.x = math.copysign(lim, o.x)
                    o.vx = -o.vx
                o.lane = int(clamp(round(o.x / C.LANE_WIDTH), -1, 1))

    # ------------------------------------------------------------------ collisions
    def _collide(self) -> None:
        p = self.player
        if self.jetpacking:
            return
        for o in self.obstacles:
            if o.hit or o.kind == "ramp":
                continue
            if not (p.z + C.PLAYER_HALF_L > o.z and p.z - C.PLAYER_HALF_L < o.z1):
                continue
            dx = abs(p.x - o.x)
            if dx >= o.half_width + C.PLAYER_HALF_W:
                continue
            if o.kind == "train":
                if p.y >= o.height - C.STEP_UP:
                    continue
            elif o.kind in ("low", "zombie"):
                if p.y >= o.height - 0.05:
                    continue
            elif o.kind == "high":
                if p.y + p.height <= C.HIGH_BARRIER_BOTTOM or p.y >= C.HIGH_BARRIER_TOP:
                    continue
            if self.invuln > 0:
                continue
            if o.kind == "zombie":
                o.hit = True
                self._hit_soft("zombie")
            elif dx >= C.FRONTAL_THRESHOLD:
                if self.bump_cooldown > 0:
                    continue
                side = 1 if p.x > o.x else -1
                p.lane = int(clamp(o.lane + side, -1, 1))
                self.bump_cooldown = 0.5
                if o.kind != "train":
                    o.hit = True
                self._hit_soft("side")
            elif o.kind == "low":
                o.hit = True
                self._hit_soft("trip")
            else:
                self.crash(o)
            if self.state != "run":
                return

    def _hit_soft(self, how: str) -> None:
        if self.board:
            self._break_board()
            return
        self.stumble(how)

    def _break_board(self) -> None:
        self.board = False
        self.invuln = 1.5
        self.emit("board_break")

    def stumble(self, how: str) -> None:
        if self.stumble_timer > 0:
            self.catch("stumble")
            return
        self.stumble_timer = C.STUMBLE_WINDOW
        self.stumbles += 1
        self.slow_timer = 0.6
        self.thief_dist = min(self.thief_dist, 4.0)
        self.player.stumble_anim = 0.5
        self.emit("stumble", how)

    def crash(self, o: Obstacle) -> None:
        p = self.player
        if self.board:
            self._break_board()
            if o.kind == "train":
                p.y = o.height + 0.05
                p.vy = 7.0
                p.grounded = False
            else:
                o.hit = True
            return
        self.catch("crash")

    def catch(self, cause: str) -> None:
        self.state = "caught"
        self.cause = cause
        self.end_time = 0.0
        self.stumbles += 1
        self.emit("crash" if cause == "crash" else "stumble", "final")
        self.emit("caught")

    def _count_passed(self) -> None:
        p = self.player
        for o in self.obstacles:
            if o.passed or o.hit or o.z1 > p.z - C.PLAYER_HALF_L:
                continue
            o.passed = True
            if abs(p.x - o.x) > o.half_width + C.PLAYER_HALF_W or self.jetpacking:
                continue
            if o.kind == "low":
                self.stats["firewalls"] += 1
            elif o.kind == "high":
                self.stats["cables"] += 1
                if p.ducking and p.duck_style == "roll":
                    self.stats["rolls"] += 1
            elif o.kind == "zombie":
                self.stats["zombies"] += 1

    # ------------------------------------------------------------------ collecting
    def _collect(self, dt: float) -> None:
        p = self.player
        mid_y = p.y + p.height * 0.5
        for f in self.pickups:
            if f.taken:
                continue
            dz = f.z - p.z
            if dz > C.MAGNET_RANGE + 2 or dz < -3:
                continue
            if self.magnet_t > 0 and -1 < dz < C.MAGNET_RANGE:
                f.attracted = True
            if f.attracted:
                k = min(1.0, dt * 10)
                f.x += (p.x - f.x) * k
                f.y += (mid_y - f.y) * k
                f.z += (p.z + 0.4 - f.z) * k
                if abs(f.x - p.x) < 0.6 and abs(f.z - p.z) < 0.9:
                    self._take(f)
                continue
            if abs(f.x - p.x) < 0.95 and abs(dz) < 0.9 and p.y - 0.4 < f.y < p.y + p.height + 0.45:
                self._take(f)
        for u in self.powerups:
            if u.taken:
                continue
            if abs(u.x - p.x) < 1.0 and abs(u.z - p.z) < 1.0 and p.y - 0.5 < u.y < p.y + p.height + 0.6:
                u.taken = True
                self.activate(u.kind)

    def activate(self, kind: str) -> None:
        if kind == "magnet":
            self.magnet_t = C.MAGNET_TIME
        elif kind == "coffee":
            self.coffee_t = C.COFFEE_TIME
        elif kind == "superjump":
            self.superjump_t = C.SUPERJUMP_TIME
        elif kind == "board":
            self.board = True
        elif kind == "jetpack":
            self.jetpack_t = C.JETPACK_TIME
            self.player.sliding = False
            self._sky_fish()
        self.stats[kind] += 1
        self.emit("powerup", kind)

    def _sky_fish(self) -> None:
        """A trail of fish high in the air while the jetpack is running."""
        p = self.player
        lane = p.lane
        z = p.z + 12
        end = p.z + self.speed * C.JETPACK_TIME * 1.1
        while z < end:
            if self.rng.random() < 0.08:
                lane = int(clamp(lane + self.rng.choice((-1, 1)), -1, 1))
            self.pickups.append(Pickup("fish", lane_x(lane), C.JETPACK_HEIGHT + 0.6, z))
            z += 2.5

    def _take(self, f: Pickup) -> None:
        f.taken = True
        if f.kind == "key":
            self.keys += 1
            self.stats["keys"] += 1
            self.score_f += 50 * self.multiplier
        else:
            value = 5 if f.kind == "golden" else 1
            self.fish_count += value
            self.stats["fish"] += value
            self.score_f += 10 * value * self.multiplier
        self.emit("pickup", (f.x, f.y, f.z, f.kind))

    def _cleanup(self) -> None:
        z = self.player.z
        self.obstacles = [o for o in self.obstacles if o.z1 > z - 40]
        self.pickups = [f for f in self.pickups if not f.taken and f.z > z - 10]
        self.powerups = [u for u in self.powerups if not u.taken and u.z > z - 10]
        self.ice = [i for i in self.ice if i.z1 > z - 20]

    # ------------------------------------------------------------------ generator
    def _generate(self) -> None:
        limit = self.player.z + C.VIEW_DISTANCE + 60
        while not self.gen_done and self.gen_z < limit:
            if not self.level.endless and self.gen_z > self.level.length - 45:
                self._fish_line(0, self.gen_z, self.level.length - self.gen_z - 5)
                self.gen_done = True
                break
            self._chunk()

    def _next_color(self) -> int:
        self._color_i += 1
        return self._color_i

    def _chunk(self) -> None:
        rng = self.rng
        start = self.gen_z
        prm = self.level.params(start)
        avail = [lane for lane in C.LANES if self.reserved[lane] <= start]
        gap = max(9.0, prm.speed * 0.65)

        if self.demo or start < 45 or rng.random() > prm.density or not avail:
            length = rng.uniform(16, 28)
            if avail:
                lane = rng.choice(avail)
            else:
                lane = min(C.LANES, key=lambda ln: self.reserved[ln])
            self._fish_line(lane, start + 3, length - 4)
            self.gen_z = start + length + gap * 0.5
            return

        options = [("barriers", 3.0)]
        if len(avail) == 3:
            options += [("trains", 3.0), ("mixed", 2.5),
                        ("moving", 6.0 * prm.moving),
                        ("zombies", 4.0 * prm.zombies),
                        ("ice", 5.0 * prm.ice), ("ice_all", 2.0 * prm.ice)]
        total = sum(w for _, w in options)
        r = rng.random() * total
        kind = options[-1][0]
        for name, w in options:
            r -= w
            if r <= 0:
                kind = name
                break
        end = getattr(self, "_chunk_" + kind)(start, avail, prm)
        self.gen_z = end + gap

    # ---- chunk patterns ------------------------------------------------
    def _chunk_barriers(self, start, avail, prm):
        rng = self.rng
        rows = rng.randint(1, 3)
        spacing = max(15.0, prm.speed * 1.0)
        z = start + 4
        for _ in range(rows):
            placed = False
            for lane in avail:
                r = rng.random()
                if r < 0.36:
                    continue
                self._barrier("low" if r < 0.7 else "high", lane, z)
                placed = True
            if not placed:
                self._barrier(rng.choice(("low", "high")), rng.choice(avail), z)
            z += spacing
        end = z - spacing + 2
        self._fish_line(rng.choice(avail), start, end - start)
        return end

    def _chunk_trains(self, start, avail, prm):
        rng = self.rng
        n = 2 if rng.random() < 0.55 else 1
        lanes = rng.sample(avail, n)
        free = [ln for ln in avail if ln not in lanes]
        end = start
        for lane in lanes:
            ramp = rng.random() < prm.ramp
            z = start + rng.uniform(0, 10) + (C.RAMP_LENGTH if ramp else 0.0)
            tr = self._train(lane, z, rng.randint(1, 3))
            if ramp:
                self.obstacles.append(Obstacle("ramp", lane, z - C.RAMP_LENGTH, C.RAMP_LENGTH, C.TRAIN_HEIGHT))
                self._fish_line(lane, z - C.RAMP_LENGTH + 1, tr.length + C.RAMP_LENGTH - 2)
            end = max(end, tr.z1)
        if free:
            self._fish_line(rng.choice(free), start, end - start)
        return end

    def _chunk_mixed(self, start, avail, prm):
        rng = self.rng
        lanes = list(avail)
        rng.shuffle(lanes)
        t_lane, b_lane, f_lane = lanes
        z = start + rng.uniform(0, 6)
        ramp = rng.random() < prm.ramp
        if ramp:
            z += C.RAMP_LENGTH
            self.obstacles.append(Obstacle("ramp", t_lane, z - C.RAMP_LENGTH, C.RAMP_LENGTH, C.TRAIN_HEIGHT))
        tr = self._train(t_lane, z, rng.randint(1, 2))
        if ramp:
            self._fish_line(t_lane, z - C.RAMP_LENGTH + 1, tr.length + C.RAMP_LENGTH - 2)
        spacing = max(15.0, prm.speed)
        bz = start + 6
        while bz < tr.z1 - 2:
            self._barrier(rng.choice(("low", "high")), b_lane, bz)
            bz += spacing * rng.uniform(1.0, 1.6)
        self._fish_line(f_lane, start, tr.z1 - start)
        return tr.z1

    def _chunk_moving(self, start, avail, prm):
        rng = self.rng
        lane = rng.choice(avail)
        others = [ln for ln in avail if ln != lane]
        cars = rng.randint(1, 2)
        v = rng.uniform(7.0, 11.0)
        zd = start + 12
        p0 = self.player.z
        s = max(5.0, (self.speed + self.level.speed_at(zd)) / 2)
        z0 = zd + v * max(0.0, zd - p0) / s
        tr = self._train(lane, z0, cars, vz=-v)
        self.reserved[lane] = tr.z1 + 8
        rng.shuffle(others)
        if rng.random() < 0.6:
            self._barrier(rng.choice(("low", "high")), others[0], zd)
        self._fish_line(others[-1], start, 30)
        return start + 30

    def _chunk_zombies(self, start, avail, prm):
        """Zombie processes shuffling across the tracks. Hitting one is only a stumble."""
        rng = self.rng
        n = rng.randint(1, 3)
        spacing = max(14.0, prm.speed * 0.9)
        z = start + 6
        for _ in range(n):
            o = Obstacle("zombie", 0, z, 0.6, C.ZOMBIE_HEIGHT)
            o.x = rng.uniform(-C.LANE_WIDTH, C.LANE_WIDTH)
            o.vx = rng.choice((-1, 1)) * rng.uniform(1.2, 2.4)
            o.lane = int(clamp(round(o.x / C.LANE_WIDTH), -1, 1))
            self.obstacles.append(o)
            z += spacing
        self._fish_line(rng.choice(avail), start, z - start)
        return z

    def _chunk_ice(self, start, avail, prm):
        rng = self.rng
        lane = rng.choice(avail)
        z = start + 3
        length = rng.uniform(14, 26)
        self.ice.append(IcePatch(lane, z, length))
        self.reserved[lane] = z + length + max(10.0, prm.speed * 0.7)
        self._fish_line(lane, z - 2, length + 2, y=0.45)
        others = [ln for ln in avail if ln != lane]
        if rng.random() < 0.6:
            self._barrier(rng.choice(("low", "high")), rng.choice(others), z + length * 0.5)
        return z + length

    def _chunk_ice_all(self, start, avail, prm):
        rng = self.rng
        z = start + 3
        length = rng.uniform(16, 28)
        self.ice.append(IcePatch(None, z, length))
        self._fish_line(rng.choice(avail), z, length, y=0.45)
        return z + length + max(10.0, prm.speed * 0.7)

    # ---- placement helpers ------------------------------------------------
    def _barrier(self, kind: str, lane: int, z: float) -> Obstacle:
        if kind == "low":
            o = Obstacle("low", lane, z, 0.35, C.LOW_BARRIER_HEIGHT)
        else:
            o = Obstacle("high", lane, z, 0.4, C.HIGH_BARRIER_TOP)
        self.obstacles.append(o)
        return o

    def _train(self, lane: int, z: float, cars: int, vz: float = 0.0) -> Obstacle:
        length = cars * C.CAR_LENGTH + (cars - 1) * C.CAR_GAP
        o = Obstacle("train", lane, z, length, C.TRAIN_HEIGHT, vz=vz, cars=cars, color=self._next_color())
        self.obstacles.append(o)
        return o

    def _fish_y(self, lane: int, z: float, base: float) -> float:
        y = base
        for o in self.obstacles:
            if o.lane != lane or o.vz or o.kind == "zombie":
                continue
            if o.kind in ("train", "ramp") and o.z - 0.5 <= z <= o.z1 + 0.5:
                y = max(y, o.surface(z) + 0.7)
            elif o.kind == "low" and abs(z - o.z) < 5.5:
                t = (z - o.z) / 5.5
                y = max(y, base + 2.0 * (1 - t * t))
            elif o.kind == "high" and abs(z - o.z) < 1.5:
                y = min(y, 0.4)
        return y

    def _fish_line(self, lane: int, z0: float, length: float, y: float = 0.7) -> None:
        if length <= 2:
            return
        rng = self.rng
        n = int(length // 3.0)
        prm = self.level.params(z0)
        special_i = rng.randrange(n) if n and rng.random() < 0.14 else -1
        special = "key" if rng.random() < 0.35 else "golden"
        power_i = n // 2 if n >= 3 and rng.random() < prm.powerup and not self.demo else -1
        for i in range(n):
            z = z0 + 1.5 + i * 3.0
            fy = self._fish_y(lane, z, y)
            if i == power_i:
                kind = rng.choice(POWERUPS)
                self.powerups.append(PowerUp(kind, lane_x(lane), fy + 0.15, z))
            else:
                kind = special if i == special_i else "fish"
                self.pickups.append(Pickup(kind, lane_x(lane), fy, z))


# --------------------------------------------------------------------------- autopilot
class Bot:
    """A simple autopilot, used for the title screen demo and automated tests."""

    def __init__(self, world: World, skill: float = 1.0) -> None:
        self.w = world
        self.cool = 0.0
        self.skill = skill

    def _threat(self, lane: int, horizon: float):
        w, p = self.w, self.w.player
        best = None
        for o in w.obstacles:
            if o.hit or o.kind == "ramp" or o.lane != lane:
                continue
            if o.z1 < p.z - 0.3:
                continue
            d = o.z - p.z
            if o.vz:
                d = d * w.speed / (w.speed - o.vz)
            if d > horizon:
                continue
            if o.kind == "train" and p.y >= o.height - C.STEP_UP and d < 1.0:
                continue
            if best is None or d < best[0]:
                best = (d, o)
        return best

    def _alongside(self, lane: int) -> bool:
        p = self.w.player
        for o in self.w.obstacles:
            if o.kind == "train" and o.lane == lane and o.z - 3 < p.z < o.z1 + 1 and p.y < o.height - C.STEP_UP:
                return True
        return False

    def _has_ramp(self, o: Obstacle) -> bool:
        return any(r.kind == "ramp" and r.lane == o.lane and abs(r.z1 - o.z) < 0.6 for r in self.w.obstacles)

    def update(self, dt: float) -> None:
        w, p = self.w, self.w.player
        if w.state != "run" or not w.can_control:
            return
        self.cool -= dt
        if self.cool > 0:
            return
        v = max(5.0, w.speed)
        cur = self._threat(p.lane, v * 1.4)
        if cur is None:
            if w.rng.random() < 0.01:
                self._fish_hunt()
            return
        d, o = cur
        if o.kind == "train" and not (self._has_ramp(o) and not o.vz):
            for lane in sorted((p.lane - 1, p.lane + 1), key=lambda ln: abs(ln)):
                if -1 <= lane <= 1 and not self._alongside(lane):
                    t = self._threat(lane, v * 1.8)
                    if t is None or t[1].kind != "train":
                        w.move(lane - p.lane)
                        self.cool = 0.2
                        return
            if not o.vz and d < v * 0.38 and p.grounded:
                w.jump()
                self.cool = 0.3
        elif o.kind in ("low", "zombie") and d < v * 0.26 + 0.8 and p.grounded:
            w.jump()
            self.cool = 0.3
        elif o.kind == "high" and d < v * 0.3 + 1.0:
            if not p.ducking:
                w.duck()
            self.cool = 0.2

    def _fish_hunt(self) -> None:
        w, p = self.w, self.w.player
        best_lane, best_n = p.lane, -1
        for lane in (p.lane - 1, p.lane, p.lane + 1):
            if not -1 <= lane <= 1 or self._alongside(lane):
                continue
            n = sum(1 for f in w.pickups if abs(f.x - lane_x(lane)) < 0.5 and 0 < f.z - p.z < 30)
            if self._threat(lane, 30):
                n -= 100
            if n > best_n:
                best_lane, best_n = lane, n
        if best_lane != p.lane:
            w.move(best_lane - p.lane)
