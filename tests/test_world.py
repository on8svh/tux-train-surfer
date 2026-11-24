"""Simulation tests (no display needed)."""

import math

from tux_train_surfer import config as C
from tux_train_surfer.levels import ENDLESS, LEVELS, level_by_number
from tux_train_surfer.world import Bot, IcePatch, Obstacle, World, lane_x


def make(level=1, seed=1):
    return World(level_by_number(level), seed=seed)


def step(w, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        w.update(dt)


def clear_track(w):
    w.obstacles.clear()
    w.ice.clear()
    w.gen_done = True


def test_jump_apex_clears_train_roof():
    apex = C.JUMP_VELOCITY ** 2 / (2 * C.GRAVITY)
    assert apex > C.TRAIN_HEIGHT - C.STEP_UP
    super_apex = C.SUPER_JUMP_VELOCITY ** 2 / (2 * C.GRAVITY)
    assert super_apex > apex + 2


def test_jump_and_land():
    w = make()
    clear_track(w)
    w.jump()
    assert not w.player.grounded
    step(w, 0.3)
    assert w.player.y > 1.5
    step(w, 1.0)
    assert w.player.grounded and w.player.y == 0


def test_lane_change_and_bounds():
    w = make()
    clear_track(w)
    w.move(-1)
    w.move(-1)
    step(w, 0.5)
    assert w.player.lane == -1
    assert abs(w.player.x - lane_x(-1)) < 1e-6


def test_frontal_train_is_caught():
    w = make()
    clear_track(w)
    w.obstacles.append(Obstacle("train", 0, w.player.z + 3, 12, C.TRAIN_HEIGHT))
    step(w, 1.0)
    assert w.state == "caught"


def test_board_saves_from_train():
    w = make()
    clear_track(w)
    w.board = True
    w.obstacles.append(Obstacle("train", 0, w.player.z + 3, 12, C.TRAIN_HEIGHT))
    step(w, 1.0)
    assert w.state == "run"
    assert not w.board


def test_ramp_leads_onto_roof():
    w = make()
    clear_track(w)
    z = w.player.z + 3
    w.obstacles.append(Obstacle("ramp", 0, z, C.RAMP_LENGTH, C.TRAIN_HEIGHT))
    w.obstacles.append(Obstacle("train", 0, z + C.RAMP_LENGTH, 24, C.TRAIN_HEIGHT))
    step(w, 1.2)
    assert w.state == "run"
    assert abs(w.player.y - C.TRAIN_HEIGHT) < 0.05


def test_low_barrier_trip_then_second_is_caught():
    w = make()
    clear_track(w)
    w.obstacles.append(Obstacle("low", 0, w.player.z + 3, 0.35, C.LOW_BARRIER_HEIGHT))
    step(w, 0.6)
    assert w.state == "run" and w.stumble_timer > 0
    w.obstacles.append(Obstacle("low", 0, w.player.z + 3, 0.35, C.LOW_BARRIER_HEIGHT))
    step(w, 0.6)
    assert w.state == "caught"


def test_jump_over_firewall_counts():
    w = make()
    clear_track(w)
    w.obstacles.append(Obstacle("low", 0, w.player.z + w.speed * 0.3, 0.35, C.LOW_BARRIER_HEIGHT))
    w.jump()
    step(w, 1.2)
    assert w.state == "run" and w.stumble_timer == 0
    assert w.stats["firewalls"] == 1


def test_duck_under_cable():
    w = make()
    clear_track(w)
    w.obstacles.append(Obstacle("high", 0, w.player.z + 4, 0.4, C.HIGH_BARRIER_TOP))
    w.duck()
    step(w, 0.6)
    assert w.state == "run"
    assert w.stats["cables"] == 1


def test_standing_into_cable_is_caught():
    w = make()
    clear_track(w)
    w.obstacles.append(Obstacle("high", 0, w.player.z + 3, 0.4, C.HIGH_BARRIER_TOP))
    step(w, 0.6)
    assert w.state == "caught"


def test_ice_locks_controls():
    w = make()
    clear_track(w)
    w.ice.append(IcePatch(0, w.player.z + 1, 20))
    step(w, 0.3)
    assert w.player.sliding
    lane = w.player.lane
    w.move(1)
    w.jump()
    assert w.player.lane == lane and w.player.grounded
    step(w, 2.0)
    assert not w.player.sliding


def test_side_bump_returns_to_lane():
    w = make()
    clear_track(w)
    w.obstacles.append(Obstacle("train", 1, w.player.z - 5, 40, C.TRAIN_HEIGHT))
    w.move(1)
    step(w, 0.5)
    assert w.player.lane == 0
    assert w.state == "run" and w.stumble_timer > 0


def test_jetpack_flies_over_everything():
    w = make()
    clear_track(w)
    w.activate("jetpack")
    w.obstacles.append(Obstacle("train", 0, w.player.z + 30, 24, C.TRAIN_HEIGHT))
    step(w, 3.0)
    assert w.state == "run"
    assert w.player.y > 4


def test_coffee_doubles_multiplier():
    w = World(level_by_number(1), seed=3, multiplier=3)
    assert w.multiplier == 3
    w.activate("coffee")
    assert w.multiplier == 6


def test_generator_keeps_a_free_lane():
    """At every point at least one lane must be free of trains."""
    for lvl in list(LEVELS) + [ENDLESS]:
        w = World(lvl, seed=42)
        w.player.z = 0
        lim = min(lvl.length, 3000) if not math.isinf(lvl.length) else 3000
        while w.gen_z < lim and not w.gen_done:
            w._chunk()
        trains = [o for o in w.obstacles if o.kind == "train" and not o.vz]
        z = 0.0
        while z < lim:
            blocked = {o.lane for o in trains if o.z - 1 <= z <= o.z1 + 1}
            assert len(blocked) < 3, (lvl.number, z)
            z += 1.0


def test_ice_lanes_have_no_obstacles():
    w = World(level_by_number(7), seed=7)
    while w.gen_z < 4000:
        w._chunk()
    for patch in w.ice:
        for o in w.obstacles:
            if o.vz or o.kind == "zombie":
                continue
            if patch.lane is None or o.lane == patch.lane:
                assert not (o.z < patch.z1 + 5 and o.z1 > patch.z), (patch, o)


def test_level_completes_with_board_spam():
    lvl = level_by_number(1)
    w = World(lvl, seed=5)
    bot = Bot(w)
    t = 0.0
    while w.state == "run" and t < 200:
        w.board = True
        bot.update(1 / 60)
        w.update(1 / 60)
        t += 1 / 60
    assert w.state == "complete"


def test_bot_survives_a_while():
    total = 0.0
    for seed in range(5):
        w = World(level_by_number(1), seed=seed)
        bot = Bot(w)
        t = 0.0
        while w.state == "run" and t < 30:
            bot.update(1 / 60)
            w.update(1 / 60)
            t += 1 / 60
        total += w.distance
    assert total / 5 > 150
