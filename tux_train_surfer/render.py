"""Pseudo-3D renderer: projects the world onto the screen and paints it back to front."""

from __future__ import annotations

import math
import random

import pygame
import pygame.gfxdraw

from . import art
from . import config as C
from .levels import THEME_ORDER, Theme
from .world import World, lane_x

GRID = 14.0  # scenery segment length


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Particle:
    __slots__ = ("x", "y", "z", "vx", "vy", "vz", "life", "max_life", "color", "size", "gravity")

    def __init__(self, x, y, z, vx, vy, vz, life, color, size, gravity=12.0):
        self.x, self.y, self.z = x, y, z
        self.vx, self.vy, self.vz = vx, vy, vz
        self.life = self.max_life = life
        self.color, self.size, self.gravity = color, size, gravity


class Renderer:
    def __init__(self, width: int, height: int) -> None:
        self.W, self.H = width, height
        self.u = height / 1080.0
        self.F = 885.0 * self.u
        self.horizon = 380.0 * self.u
        self.cx = width / 2
        self.cam_x, self.cam_y, self.cam_z = 0.0, C.CAMERA_HEIGHT, -C.CAMERA_BACK
        self.shake = 0.0
        self.theme: Theme | None = None
        self._bg: dict[str, pygame.Surface] = {}
        self._fish: dict = {}
        self._pu: dict = {}
        self._sprite: dict = {}
        self._glow: dict = {}
        self.particles: list[Particle] = []
        self.snow = [[random.random() * width, random.random() * height, random.uniform(0.5, 1.0)]
                     for _ in range(220)]
        self.t = 0.0
        self.fog_rgb = (200, 220, 240)
        self._fogc: dict = {}
        self._shades: dict = {}

    # ------------------------------------------------------------------ camera
    def reset_camera(self, world: World) -> None:
        p = world.player
        self.cam_x = p.x * 0.7
        self.cam_y = C.CAMERA_HEIGHT + p.y * 0.6
        self.cam_z = p.z - C.CAMERA_BACK

    def follow(self, world: World, dt: float) -> None:
        p = world.player
        k = min(1.0, dt * 8)
        self.cam_x += (p.x * 0.7 - self.cam_x) * k
        self.cam_y += (C.CAMERA_HEIGHT + p.y * 0.6 - self.cam_y) * min(1.0, dt * 5)
        self.cam_z = p.z - C.CAMERA_BACK
        self.shake = max(0.0, self.shake - dt)

    def proj(self, x, y, z):
        dz = z - self.cam_z
        if dz < C.NEAR_PLANE * 0.99:
            dz = C.NEAR_PLANE
        s = self.F / dz
        return self.cx + (x - self.cam_x) * s, self.horizon + (self.cam_y - y) * s

    def scale_at(self, z):
        return self.F / max(C.NEAR_PLANE, z - self.cam_z)

    def near_z(self):
        return self.cam_z + C.NEAR_PLANE

    # ------------------------------------------------------------------ colour helpers
    _FOG_STEPS = 40

    def fog(self, color, z):
        t = (z - self.cam_z - C.FOG_START) / (C.VIEW_DISTANCE - C.FOG_START)
        if t <= 0:
            return color[:3]
        b = int(min(1.0, t) * self._FOG_STEPS)
        key = (color, b, self.fog_rgb)
        c = self._fogc.get(key)
        if c is None:
            if len(self._fogc) > 5000:
                self._fogc.clear()
            c = lerp(color, self.fog_rgb, (b / self._FOG_STEPS) ** 1.15)
            self._fogc[key] = c
        return c

    # ------------------------------------------------------------------ primitives
    def _poly(self, surf, color, pts):
        p = [(int(clamp(x, -30000, 30000)), int(clamp(y, -30000, 30000))) for x, y in pts]
        pygame.gfxdraw.filled_polygon(surf, p, color)
        pygame.gfxdraw.aapolygon(surf, p, color)

    def quad(self, surf, color, pts3, fog_z=None):
        """Project a flat polygon given in world space and fill it (hot path, kept lean)."""
        cx, hz, F = self.cx, self.horizon, self.F
        camx, camy, camz = self.cam_x, self.cam_y, self.cam_z
        near = C.NEAR_PLANE
        out = []
        zsum = 0.0
        minx = miny = 1e9
        maxx = maxy = -1e9
        for x, y, z in pts3:
            dz = z - camz
            if dz < near:
                dz = near
            s = F / dz
            sx = cx + (x - camx) * s
            sy = hz + (camy - y) * s
            if sx < minx:
                minx = sx
            if sx > maxx:
                maxx = sx
            if sy < miny:
                miny = sy
            if sy > maxy:
                maxy = sy
            out.append((sx, sy))
            zsum += z
        if maxx < 0 or minx > self.W or maxy < 0 or miny > self.H:
            return
        if minx < -30000 or maxx > 30000 or miny < -30000 or maxy > 30000:
            out = [(max(-30000, min(30000, a)), max(-30000, min(30000, b))) for a, b in out]
        pts = [(int(a), int(b)) for a, b in out]
        col = self.fog(color, zsum / len(pts3) if fog_z is None else fog_z)
        pygame.gfxdraw.filled_polygon(surf, pts, col)
        w, h = maxx - minx, maxy - miny
        # anti-aliased edges cost as much as the fill on huge faces and are invisible there
        if w > 3 and h > 3 and (w < 500 or h < 140):
            pygame.gfxdraw.aapolygon(surf, pts, col)

    def box(self, surf, x0, x1, y0, y1, z0, z1, color, top=None, side=None, front=None):
        """Axis-aligned box. Returns the visible side ('l'/'r'/None) and whether the front is real."""
        nz = self.near_z()
        if z1 <= nz:
            return None, False
        clipped = z0 < nz
        z0 = max(z0, nz)
        if top is None or side is None:
            sh = self._shades.get(color)
            if sh is None:
                sh = (art.shade(color, 1.15), art.shade(color, 0.78))
                self._shades[color] = sh
            top = top or sh[0]
            side = side or sh[1]
        front = front or color
        vis_side = None
        if self.cam_x < x0:
            self.quad(surf, side, [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)])
            vis_side = "l"
        elif self.cam_x > x1:
            self.quad(surf, side, [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)])
            vis_side = "r"
        if self.cam_y > y1:
            self.quad(surf, top, [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)])
        elif self.cam_y < y0:
            self.quad(surf, art.shade(color, 0.6), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)])
        if not clipped:
            self.quad(surf, front, [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], z0)
        return vis_side, not clipped

    def glow(self, surf, x, y, z, radius_m, color):
        s = self.scale_at(z)
        r = int(radius_m * s)
        if r < 2 or r > 600:
            return
        key = ("glow", r // 2 * 2, color)
        g = self._glow.get(key)
        if g is None:
            rr = key[1]
            # additive blending ignores alpha, so brightness is baked into the colour
            g = pygame.Surface((rr * 2, rr * 2))
            g.fill((0, 0, 0))
            for i in range(10, 0, -1):
                f = ((10 - i + 1) / 10) ** 2 * 0.55
                pygame.draw.circle(g, tuple(int(c * f) for c in color), (rr, rr), max(1, int(rr * i / 10)))
            if len(self._glow) > 300:
                self._glow.clear()
            self._glow[key] = g
        sx, sy = self.proj(x, y, z)
        surf.blit(g, (sx - key[1], sy - key[1]), special_flags=pygame.BLEND_ADD)

    # ------------------------------------------------------------------ background
    def background(self, theme: Theme) -> pygame.Surface:
        bg = self._bg.get(theme.key)
        if bg is not None:
            return bg
        W, H, hz = self.W, self.H, int(self.horizon)
        margin = int(120 * self.u)
        bg = pygame.Surface((W + margin * 2, H))
        for y in range(hz + 1):
            t = y / max(1, hz)
            pygame.draw.line(bg, lerp(theme.sky_top, theme.sky_bottom, t ** 1.3), (0, y), (W + margin * 2, y))
        rng = random.Random(THEME_ORDER.index(theme.key) if theme.key in THEME_ORDER else 1)
        if theme.stars:
            for _ in range(int(260 * self.u) + 60):
                x, y = rng.uniform(0, W + margin * 2), rng.uniform(0, hz * 0.85)
                b = rng.randint(150, 255)
                pygame.draw.circle(bg, (b, b, b), (int(x), int(y)), rng.choice((1, 1, 1, 2)))
        if theme.aurora:
            aur = pygame.Surface(bg.get_size(), pygame.SRCALPHA)
            for band in range(3):
                col = ((80, 255, 160), (120, 220, 255), (200, 120, 255))[band]
                base = hz * (0.25 + band * 0.12)
                for i in range(0, W + margin * 2, max(2, int(6 * self.u))):
                    wave = math.sin(i * 0.004 + band * 2) * 40 * self.u + math.sin(i * 0.011 + band) * 18 * self.u
                    top = base + wave
                    hgt = (90 + 50 * math.sin(i * 0.007 + band)) * self.u
                    pygame.draw.line(aur, (*col, 40), (i, top), (i, top + hgt), max(2, int(6 * self.u)))
                    pygame.draw.line(aur, (*col, 60), (i, top + hgt * 0.6), (i, top + hgt), max(2, int(6 * self.u)))
            bg.blit(aur, (0, 0))
        if theme.celestial != "none":
            cx, cy = int((W + margin * 2) * 0.72), int(hz * 0.35)
            r = int(60 * self.u)
            for i in range(6, 0, -1):
                glow = pygame.Surface((r * 6, r * 6), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*theme.celestial_color, 18), (r * 3, r * 3), int(r * (1 + i * 0.35)))
                bg.blit(glow, (cx - r * 3, cy - r * 3))
            pygame.draw.circle(bg, theme.celestial_color, (cx, cy), r)
            if theme.celestial == "moon":
                pygame.draw.circle(bg, art.shade(theme.celestial_color, 0.88), (cx - r // 3, cy - r // 4), r // 4)
                pygame.draw.circle(bg, art.shade(theme.celestial_color, 0.9), (cx + r // 3, cy + r // 3), r // 6)
        # mountains (two layers)
        for layer in range(2):
            col = lerp(theme.mountains, theme.fog, 0.45 if layer == 0 else 0.15)
            pts = [(0, hz)]
            x = 0.0
            while x < W + margin * 2:
                x += rng.uniform(60, 160) * self.u
                peak = rng.uniform(40, 150 if layer == 0 else 90) * self.u
                pts.append((x, hz - peak))
                if not theme.tunnel and layer == 0 and peak > 90 * self.u:
                    pass
            pts.append((W + margin * 2, hz))
            pygame.draw.polygon(bg, col, pts)
            if layer == 0 and not theme.night:
                for i in range(1, len(pts) - 1):
                    px, py = pts[i]
                    if hz - py > 80 * self.u:
                        cap = 22 * self.u
                        pygame.draw.polygon(bg, (250, 252, 255), [(px, py), (px - cap, py + cap * 0.9),
                                                                 (px + cap, py + cap * 0.9)])
        if theme.volcano:
            vx = (W + margin * 2) * 0.3
            vw, vh = 330 * self.u, 210 * self.u
            pygame.draw.polygon(bg, (70, 65, 70), [(vx - vw, hz), (vx - vw * 0.18, hz - vh),
                                                   (vx + vw * 0.18, hz - vh), (vx + vw, hz)])
            pygame.draw.polygon(bg, (240, 244, 250), [(vx - vw * 0.32, hz - vh * 0.6), (vx - vw * 0.18, hz - vh),
                                                      (vx + vw * 0.18, hz - vh), (vx + vw * 0.3, hz - vh * 0.62),
                                                      (vx + vw * 0.1, hz - vh * 0.72), (vx - vw * 0.1, hz - vh * 0.66)])
            pygame.draw.polygon(bg, (255, 120, 40), [(vx - vw * 0.12, hz - vh), (vx + vw * 0.12, hz - vh),
                                                     (vx + vw * 0.05, hz - vh * 0.88), (vx - vw * 0.04, hz - vh * 0.9)])
            smoke = pygame.Surface(bg.get_size(), pygame.SRCALPHA)
            for i in range(9):
                r = int((40 + i * 14) * self.u)
                pygame.draw.circle(smoke, (120, 115, 120, 70), (int(vx + i * 26 * self.u), int(hz - vh - i * 32 * self.u)), r)
            bg.blit(smoke, (0, 0))
        # ground gradient
        for y in range(hz, H):
            dz = C.CAMERA_HEIGHT * self.F / max(1.0, y - self.horizon)
            t = clamp((dz - C.FOG_START) / (C.VIEW_DISTANCE - C.FOG_START), 0.0, 1.0)
            pygame.draw.line(bg, lerp(theme.ground, theme.fog, t ** 1.15), (0, y), (W + margin * 2, y))
        if theme.tunnel:
            dark = pygame.Surface(bg.get_size(), pygame.SRCALPHA)
            dark.fill((10, 20, 35, 120))
            bg.blit(dark, (0, 0))
        bg = bg.convert() if pygame.display.get_surface() else bg
        self._bg[theme.key] = bg
        return bg

    # ------------------------------------------------------------------ main entry
    def draw(self, surf: pygame.Surface, world: World, t: float, dt: float = 0.0) -> None:
        self.t = t
        theme = world.theme
        self.theme = theme
        self.fog_rgb = theme.fog
        bg = self.background(theme)
        margin = (bg.get_width() - self.W) // 2
        ox = -margin - clamp(self.cam_x * 18 * self.u, -margin, margin)
        sh = (math.sin(t * 70) * 10 * self.u * self.shake) if self.shake > 0 else 0
        surf.blit(bg, (ox + sh, 0))
        self._draw_track(surf, world)
        if theme.tunnel:
            self._draw_tunnel(surf)
        items = []
        self._collect_scenery(items, world)
        self._collect_objects(items, world)
        items.sort(key=lambda it: -it[0])
        for _, _, fn, args in items:
            fn(surf, *args)
        self._draw_particles(surf, dt)
        if theme.snow > 0:
            self._draw_snow(surf, theme.snow, dt, world.speed)
        if theme.night:
            self._vignette(surf, 90)

    # ------------------------------------------------------------------ track
    def _draw_track(self, surf, world: World):
        th = self.theme
        nz = self.near_z()
        far = self.cam_z + C.VIEW_DISTANCE
        # long ground strips are split only where the fog colour changes noticeably
        cuts = [nz] + [self.cam_z + d for d in (C.FOG_START + 10, 95, 130) if self.cam_z + d > nz] + [far]
        segs = list(zip(cuts, cuts[1:]))
        self._segs = segs
        curb = art.shade(th.gravel, 1.25)
        for side in (-1, 1):
            x0 = side * 3.75
            x1 = side * 4.3
            for z, z2 in segs:
                self.quad(surf, curb, [(x0, 0, z), (x1, 0, z), (x1, 0, z2), (x0, 0, z2)])
        for lane in C.LANES:
            lx = lane_x(lane)
            for z, z2 in segs:
                self.quad(surf, th.gravel, [(lx - 1.2, 0, z), (lx + 1.2, 0, z), (lx + 1.2, 0, z2), (lx - 1.2, 0, z2)])
        if th.grid:
            # glowing terminal grid
            gz = math.floor(nz / 6.0) * 6.0 + 6.0
            while gz < far:
                self.quad(surf, (0, 90, 40), [(-12, 0.005, gz), (12, 0.005, gz), (12, 0.005, gz + 0.12), (-12, 0.005, gz + 0.12)])
                gz += 6.0
            for gx in (-11.0, -8.0, -5.5, 5.5, 8.0, 11.0):
                self.quad(surf, (0, 90, 40), [(gx - 0.06, 0.005, nz), (gx + 0.06, 0.005, nz),
                                              (gx + 0.06, 0.005, far), (gx - 0.06, 0.005, far)], nz + 30)
        # sleepers
        step = 1.6
        z = math.floor(nz / step) * step + step
        sleeper_far = self.cam_z + (62 if th.rails == "steel" else 0)
        thin_from = self.cam_z + 30
        while z < sleeper_far:
            if z < thin_from or int(round(z / step)) % 2 == 0:
                for lane in C.LANES:
                    lx = lane_x(lane)
                    self.quad(surf, th.sleeper, [(lx - 1.0, 0, z), (lx + 1.0, 0, z), (lx + 1.0, 0, z + 0.38),
                                                 (lx - 1.0, 0, z + 0.38)])
            z += step
        # ice patches (on the ground, below everything)
        for patch in world.ice:
            z0, z1 = max(patch.z, nz), min(patch.z1, far)
            if z1 <= z0:
                continue
            if patch.lane is None:
                xa, xb = -3.8, 3.8
            else:
                lx = lane_x(patch.lane)
                xa, xb = lx - 1.3, lx + 1.3
            self.quad(surf, (185, 225, 248), [(xa, 0.02, z0), (xb, 0.02, z0), (xb, 0.02, z1), (xa, 0.02, z1)])
            # shiny streaks
            rng = random.Random(int(patch.z * 10))
            for _ in range(int((patch.z1 - patch.z) / 2.5)):
                sz = rng.uniform(patch.z, patch.z1 - 2)
                if sz < nz or sz > far:
                    continue
                sx = rng.uniform(xa + 0.3, xb - 0.8)
                self.quad(surf, (245, 252, 255), [(sx, 0.03, sz), (sx + 0.5, 0.03, sz + 0.2),
                                                  (sx + 0.6, 0.03, sz + 1.2), (sx + 0.1, 0.03, sz + 1.0)])
        if th.rails == "data":
            self._data_streams(surf, nz, far)
            return
        # rails
        for lane in C.LANES:
            lx = lane_x(lane)
            for rx in (lx - 0.72, lx + 0.72):
                for z, z2 in segs:
                    self.quad(surf, th.rail, [(rx - 0.06, 0.12, z), (rx + 0.06, 0.12, z), (rx + 0.06, 0.12, z2),
                                              (rx - 0.06, 0.12, z2)])

    def _data_streams(self, surf, nz, far):
        """Terminal railway: glowing data streams with packets racing along instead of steel rails."""
        for lane in C.LANES:
            lx = lane_x(lane)
            for rx in (lx - 0.72, lx + 0.72):
                self.quad(surf, (0, 150, 60), [(rx - 0.09, 0.02, nz), (rx + 0.09, 0.02, nz),
                                               (rx + 0.09, 0.02, far), (rx - 0.09, 0.02, far)], nz + 20)
                self.quad(surf, (120, 255, 160), [(rx - 0.03, 0.03, nz), (rx + 0.03, 0.03, nz),
                                                  (rx + 0.03, 0.03, far), (rx - 0.03, 0.03, far)], nz + 20)
            # packets travelling towards the horizon
            rng = random.Random(lane + 11)
            offset = (self.t * 35) % 9.0
            z = math.floor(nz / 9.0) * 9.0 + offset
            while z < self.cam_z + 110:
                for rx in (lx - 0.72, lx + 0.72):
                    if z > nz:
                        col = (200, 255, 210) if rng.random() < 0.5 else (60, 255, 120)
                        self.quad(surf, col, [(rx - 0.14, 0.04, z), (rx + 0.14, 0.04, z),
                                              (rx + 0.14, 0.04, z + 1.2), (rx - 0.14, 0.04, z + 1.2)])
                z += 9.0 if z < self.cam_z + 40 else 18.0
            # binary "sleepers"
            if True:
                z = math.floor(nz / 4.0) * 4.0 + 4.0
                while z < self.cam_z + 60:
                    s = self.scale_at(z)
                    size = int(0.55 * s)
                    if size >= 8:
                        bit = "1" if int(z / 4.0 + lane) % 3 else "0"
                        img = self._text_img(bit, size, (0, 120, 50))
                        px, py = self.proj(lx, 0.0, z)
                        surf.blit(img, img.get_rect(center=(px, py)))
                    z += 4.0

    def _text_img(self, text, size, color):
        key = ("txt", text, size // 2 * 2, color)
        img = self._glow.get(key)
        if img is None:
            if len(self._glow) > 600:
                self._glow.clear()
            img = getattr(self, "font_func", _font)(max(6, size // 2 * 2)).render(text, True, color)
            self._glow[key] = img
        return img

    # ------------------------------------------------------------------ scenery
    def _collect_scenery(self, items, world):
        th = self.theme
        seed = THEME_ORDER.index(th.key) if th.key in THEME_ORDER else 0
        k0 = int(math.floor((self.cam_z - GRID) / GRID))
        k1 = int((self.cam_z + C.VIEW_DISTANCE) / GRID) + 1
        for k in range(k0, k1):
            for side in (-1, 1):
                rng = random.Random(k * 7919 + side * 104729 + seed * 31)
                if rng.random() < 0.28 or th.tunnel == "rack":
                    continue
                kind = rng.choice(th.scenery)
                # inside a tunnel the decorations stand in front of the wall
                x = side * (rng.uniform(4.5, 4.9) if th.tunnel else rng.uniform(5.6, 9.5))
                z = k * GRID + rng.uniform(0, GRID * 0.5)
                if z < self.near_z() + 1 or z > self.cam_z + C.VIEW_DISTANCE:
                    continue
                items.append((z + 2, abs(x), getattr(self, "_sc_" + kind), (x, z, side, rng.random())))
        if not world.level.endless:
            zf = world.level.length
            if self.near_z() < zf < self.cam_z + C.VIEW_DISTANCE:
                items.append((zf + 1, 0, self._finish, (zf,)))

    def _draw_tunnel(self, surf):
        """Tunnel walls and ceiling, drawn in the background pass as a few long faces."""
        nz = self.near_z()
        rack = self.theme.tunnel == "rack"
        wall = (30, 34, 42) if rack else (55, 80, 105)
        ceiling = (22, 25, 32) if rack else (35, 55, 75)
        for z0, z1 in self._segs:
            for side in (-1, 1):
                x = side * 5.2
                self.quad(surf, art.shade(wall, 0.85 if side < 0 else 0.75),
                          [(x, 0, z0), (x, 6.5, z0), (x, 6.5, z1), (x, 0, z1)])
            self.quad(surf, ceiling, [(-5.2, 6.5, z0), (5.2, 6.5, z0), (5.2, 6.5, z1), (-5.2, 6.5, z1)])
            if rack:
                for cx in (-2.5, 0.0, 2.5):  # cable trays
                    self.quad(surf, (50, 55, 65), [(cx - 0.4, 6.3, z0), (cx + 0.4, 6.3, z0), (cx + 0.4, 6.3, z1), (cx - 0.4, 6.3, z1)])
        leds = ((40, 255, 90), (255, 190, 40), (60, 160, 255), (255, 60, 60))
        k0 = int(math.floor(self.cam_z / GRID))
        k1 = int((self.cam_z + C.VIEW_DISTANCE) / GRID) + 1
        for k in range(k1, k0 - 1, -1):  # far to near
            z = k * GRID
            if z <= nz:
                continue
            dist = z - self.cam_z
            if rack:
                if dist < 110:
                    for side in (-1, 1):
                        xi = side * 5.18
                        for j in range(3):
                            zz = z + j * (GRID / 3)
                            self.quad(surf, (70, 75, 88), [(xi, 0, zz), (xi, 6.5, zz), (xi, 6.5, zz + 0.25), (xi, 0, zz + 0.25)])
                        if dist < 50:
                            for row in range(4):
                                y = 0.9 + row * 1.25
                                for col in range(5):
                                    zz = z + 0.8 + col * (GRID - 1.6) / 5
                                    h = (row * 7 + col * 13 + k * 5 + side) % 17
                                    if (int(self.t * (3 + h % 4)) + h) % 4 == 0:
                                        continue
                                    self.quad(surf, leds[h % 4], [(xi, y, zz), (xi, y + 0.12, zz), (xi, y + 0.12, zz + 0.25), (xi, y, zz + 0.25)])
                if dist > 8:
                    self.glow(surf, 0, 6.0, z + 0.1, 1.2, (40, 90, 160))
            else:
                self.quad(surf, (25, 40, 55), [(-5.2, 6.5, z), (5.2, 6.5, z), (5.2, 6.2, z), (-5.2, 6.2, z)])
                if dist > 8:
                    self.glow(surf, 0, 6.1, z + 0.1, 1.4, (120, 200, 255))

    def _sc_pine(self, surf, x, z, side, r):
        h = 4 + r * 4
        self.box(surf, x - 0.2, x + 0.2, 0, h * 0.25, z, z + 0.4, (100, 70, 45))
        green = (40, 110, 70) if not self.theme.night else (25, 65, 50)
        for i in range(3):
            y0 = h * (0.2 + i * 0.25)
            w = (1.9 - i * 0.5) * (0.8 + r * 0.4)
            top = y0 + h * 0.38
            pts = [(x - w, y0, z), (x + w, y0, z), (x, top, z)]
            self.quad(surf, green, pts, z)
            self.quad(surf, (245, 250, 255), [(x - w * 0.35, top - h * 0.13, z), (x + w * 0.35, top - h * 0.13, z),
                                              (x, top, z)], z)

    def _sc_house(self, surf, x, z, side, r):
        colors = ((200, 80, 70), (230, 190, 90), (110, 150, 200), (150, 200, 150), (235, 235, 230))
        col = colors[int(r * 5) % 5]
        w = 2.3
        vis, front = self.box(surf, x - w, x + w, 0, 3.0, z, z + 5, col)
        win = (255, 220, 120) if self.theme.night else (120, 170, 210)
        if front:
            for wx in (x - 1.2, x + 1.2):
                self.quad(surf, win, [(wx - 0.45, 1.3, z), (wx + 0.45, 1.3, z), (wx + 0.45, 2.2, z), (wx - 0.45, 2.2, z)], z)
            self.quad(surf, (90, 60, 45), [(x - 0.4, 0, z), (x + 0.4, 0, z), (x + 0.4, 1.7, z), (x - 0.4, 1.7, z)], z)
            if self.theme.night:
                self.glow(surf, x - 1.2, 1.75, z - 0.1, 1.2, (90, 70, 20))
        nz = self.near_z()
        if z > nz:
            roof = (160, 60, 55) if int(r * 7) % 2 else (90, 90, 110)
            self.quad(surf, art.shade(roof, 0.8), [(x - w - 0.2, 3.0, z), (x + w + 0.2, 3.0, z), (x, 4.6, z)], z)
            self.quad(surf, (250, 252, 255), [(x - 1.0, 3.85, z), (x + 1.0, 3.85, z), (x, 4.6, z)], z)
        z0 = max(z, nz)
        if z + 5 > nz:
            xs = x - w - 0.2 if side > 0 else x + w + 0.2
            self.quad(surf, (245, 248, 255), [(xs, 3.0, z0), (x, 4.6, z0), (x, 4.6, z + 5), (xs, 3.0, z + 5)])

    def _sc_igloo(self, surf, x, z, side, r):
        if z < self.near_z():
            return
        rad = 1.8 + r
        pts = [(x + math.cos(a) * rad, math.sin(a) * rad * 0.9, z) for a in
               [i * math.pi / 16 for i in range(17)]]
        self.quad(surf, (235, 243, 252), pts, z)
        for i in range(1, 3):
            yy = rad * 0.9 * i / 3
            hw = math.sqrt(max(0.0, rad * rad - (yy / 0.9) ** 2))
            self.quad(surf, (200, 215, 235), [(x - hw, yy, z), (x + hw, yy, z), (x + hw, yy + 0.06, z),
                                              (x - hw, yy + 0.06, z)], z)
        door = [(x + math.cos(a) * 0.6, math.sin(a) * 0.9, z) for a in [i * math.pi / 8 for i in range(9)]]
        self.quad(surf, (60, 70, 90), door, z)

    def _sc_lamp(self, surf, x, z, side, r):
        self.box(surf, x - 0.08, x + 0.08, 0, 4.5, z, z + 0.16, (70, 75, 90))
        hx = x - side * 0.6
        self.box(surf, min(x, hx) - 0.1, max(x, hx) + 0.1, 4.4, 4.55, z, z + 0.2, (70, 75, 90))
        self.box(surf, hx - 0.25, hx + 0.25, 4.2, 4.4, z, z + 0.3, (230, 230, 200))
        if self.theme.night:
            self.glow(surf, hx, 4.2, z, 2.2, (110, 100, 50))

    def _sc_fence(self, surf, x, z, side, r):
        col = (150, 110, 80)
        rail = (165, 121, 88)
        nz = self.near_z()
        for i in range(4):
            zz = z + i * 2.2
            if zz > nz:
                self.quad(surf, col, [(x - 0.09, 0, zz), (x + 0.09, 0, zz), (x + 0.09, 1.2, zz), (x - 0.09, 1.2, zz)], zz)
        z0 = max(z, nz)
        if z + 6.8 > z0:
            for ya, yb in ((0.75, 0.95), (0.25, 0.45)):
                self.quad(surf, rail, [(x, ya, z0), (x, yb, z0), (x, yb, z + 6.8), (x, ya, z + 6.8)])

    def _sc_snowman(self, surf, x, z, side, r):
        if z < self.near_z():
            return
        for cy, rad in ((0.55, 0.6), (1.4, 0.43), (2.05, 0.3)):
            pts = [(x + math.cos(a) * rad, cy + math.sin(a) * rad, z) for a in
                   [i * math.tau / 20 for i in range(20)]]
            self.quad(surf, (245, 248, 255), pts, z)
        self.quad(surf, (250, 140, 30), [(x, 2.08, z), (x, 2.0, z), (x - side * 0.35, 2.03, z)], z)
        self.quad(surf, (30, 30, 35), [(x - 0.25, 2.3, z), (x + 0.25, 2.3, z), (x + 0.2, 2.75, z), (x - 0.2, 2.75, z)], z)

    def _sc_crane(self, surf, x, z, side, r):
        yel = (240, 180, 40)
        self.box(surf, x - 0.35, x + 0.35, 0, 11, z, z + 0.7, yel)
        arm_x = x - side * 5
        self.box(surf, min(x, arm_x) - 0.3, max(x, arm_x) + 0.3, 10.2, 10.8, z, z + 0.6, yel)
        self.box(surf, arm_x - 0.03, arm_x + 0.03, 6, 10.2, z + 0.2, z + 0.3, (60, 60, 60))
        self.box(surf, arm_x - 0.6, arm_x + 0.6, 5.4, 6.0, z - 0.3, z + 0.9, (90, 90, 100))

    def _sc_container(self, surf, x, z, side, r):
        cols = ((200, 60, 50), (40, 120, 180), (60, 150, 90), (220, 140, 40))
        col = cols[int(r * 4) % 4]
        self.box(surf, x - 1.3, x + 1.3, 0, 2.6, z, z + 6.0, col)
        if r > 0.5:
            col2 = cols[int(r * 13) % 4]
            self.box(surf, x - 1.3, x + 1.3, 2.6, 5.2, z + 0.5, z + 6.5, col2)

    def _sc_iceberg(self, surf, x, z, side, r):
        if z < self.near_z():
            return
        h = 3 + r * 5
        pts = [(x - 3, 0, z), (x - 2.2, h * 0.6, z), (x - 0.8, h, z), (x + 0.4, h * 0.75, z),
               (x + 1.6, h * 0.9, z), (x + 3, 0, z)]
        self.quad(surf, (210, 235, 250), pts, z)
        self.quad(surf, (170, 210, 240), [(x - 0.8, h, z), (x + 0.4, h * 0.75, z), (x + 0.2, 0, z), (x - 1.4, 0, z)], z)

    def _sc_crystal(self, surf, x, z, side, r):
        if z < self.near_z():
            return
        col = (100, 220, 255) if r > 0.5 else (190, 140, 255)
        for i in range(3):
            cx = x + (i - 1) * 0.6
            h = 1.2 + ((r * 7 + i) % 1.0) * 2.0
            self.quad(surf, col, [(cx - 0.3, 0, z), (cx + 0.3, 0, z), (cx + 0.1, h, z), (cx - 0.05, h + 0.3, z)], z)
        self.glow(surf, x, 1.0, z - 0.2, 2.0, tuple(c // 3 for c in col))

    def _sc_colony(self, surf, x, z, side, r):
        """A little colony of penguins watching the race."""
        if z < self.near_z():
            return
        rng = random.Random(int(r * 1000))
        for i in range(5):
            px = x + rng.uniform(-2.2, 2.2)
            pz = z + rng.uniform(0, 3)
            h = rng.uniform(0.55, 0.8)
            self.quad(surf, (25, 27, 35), [(px + math.cos(a) * h * 0.35, h * 0.5 + math.sin(a) * h * 0.5, pz)
                                           for a in [k * math.tau / 14 for k in range(14)]], pz)
            self.quad(surf, (245, 245, 250), [(px + math.cos(a) * h * 0.22, h * 0.42 + math.sin(a) * h * 0.36, pz - 0.01)
                                              for a in [k * math.tau / 12 for k in range(12)]], pz)
            self.quad(surf, (25, 27, 35), [(px + math.cos(a) * h * 0.2, h * 1.05 + math.sin(a) * h * 0.2, pz)
                                           for a in [k * math.tau / 10 for k in range(10)]], pz)
            flap = math.sin(self.t * 6 + i) * 0.1 if (i + int(self.t)) % 3 == 0 else 0
            self.quad(surf, (250, 165, 30), [(px - 0.06, h * 1.0, pz - 0.02), (px + 0.06, h * 1.0, pz - 0.02),
                                             (px, h * 0.9 - flap, pz - 0.02)], pz)

    def _sc_station(self, surf, x, z, side, r):
        vis, front = self.box(surf, x - 2.0, x + 2.0, 0.4, 3.0, z, z + 6, (200, 60, 40))
        self.box(surf, x - 1.8, x + 1.8, 0, 0.4, z + 0.3, z + 5.7, (90, 90, 100))
        if front:
            for wx in (x - 1.1, x + 1.1):
                self.quad(surf, (150, 200, 230), [(wx - 0.4, 1.5, z), (wx + 0.4, 1.5, z), (wx + 0.4, 2.3, z), (wx - 0.4, 2.3, z)], z)
        self.box(surf, x + 1.2, x + 1.3, 3.0, 5.5, z + 2, z + 2.1, (200, 200, 210))
        self.box(surf, x + 0.6, x + 1.9, 5.3, 5.4, z + 1.95, z + 2.15, (200, 200, 210))

    def _sc_flag(self, surf, x, z, side, r):
        self.box(surf, x - 0.05, x + 0.05, 0, 4.0, z, z + 0.1, (200, 200, 210))
        if z > self.near_z():
            wave = math.sin(self.t * 5) * 0.15
            col = ((40, 110, 200), (230, 60, 60), (250, 200, 40))[int(r * 3) % 3]
            self.quad(surf, col, [(x, 4.0, z), (x - side * 1.6, 3.9 + wave, z), (x - side * 1.6, 3.1 + wave, z), (x, 3.2, z)], z)

    def _sc_geyser(self, surf, x, z, side, r):
        if z < self.near_z():
            return
        self.quad(surf, (110, 160, 170), [(x + math.cos(a) * 1.4, 0.02, z + math.sin(a) * 1.0)
                                          for a in [k * math.tau / 12 for k in range(12)]], z)
        cycle = (self.t * 0.6 + r * 10) % 4.0
        if cycle < 1.6:
            h = math.sin(cycle / 1.6 * math.pi) * (7 + r * 5)
            w = 0.35 + h * 0.04
            self.quad(surf, (235, 245, 250), [(x - w, 0, z), (x + w, 0, z), (x + w * 2.2, h, z), (x - w * 2.2, h, z)], z)
            self.quad(surf, (250, 252, 255), [(x - w * 0.5, 0, z), (x + w * 0.5, 0, z), (x + w, h * 1.05, z), (x - w, h * 1.05, z)], z)
        else:
            self.quad(surf, (220, 230, 235), [(x - 0.6, 0, z), (x + 0.6, 0, z), (x + 1.0, 1.0, z), (x - 1.0, 1.0, z)], z)

    def _sc_turfhouse(self, surf, x, z, side, r):
        vis, front = self.box(surf, x - 1.8, x + 1.8, 0, 1.8, z, z + 4, (240, 240, 235))
        if front:
            self.quad(surf, (180, 40, 40), [(x - 0.4, 0, z), (x + 0.4, 0, z), (x + 0.4, 1.4, z), (x - 0.4, 1.4, z)], z)
        if z > self.near_z():
            self.quad(surf, (90, 140, 70), [(x - 2.0, 1.8, z), (x + 2.0, 1.8, z), (x, 3.4, z)], z)
        z0 = max(z, self.near_z())
        if z + 4 > z0:
            xs = x - 2.0 if side > 0 else x + 2.0
            self.quad(surf, (110, 160, 80), [(xs, 1.8, z0), (x, 3.4, z0), (x, 3.4, z + 4), (xs, 1.8, z + 4)])

    def _sc_volcano_rock(self, surf, x, z, side, r):
        if z < self.near_z():
            return
        h = 1.2 + r * 2.5
        self.quad(surf, (55, 55, 60), [(x - 2, 0, z), (x - 1.2, h * 0.7, z), (x - 0.2, h, z), (x + 1.0, h * 0.6, z), (x + 2, 0, z)], z)
        self.quad(surf, (90, 140, 70), [(x - 1.6, 0.6, z), (x - 1.2, h * 0.7, z), (x - 0.2, h, z), (x + 0.2, h * 0.8, z), (x - 0.4, 0.4, z)], z)

    def _sc_moss(self, surf, x, z, side, r):
        if z < self.near_z():
            return
        self.quad(surf, (100, 150, 80), [(x + math.cos(a) * 2.5, 0.01, z + 2 + math.sin(a) * 2.0)
                                         for a in [k * math.tau / 10 for k in range(10)]], z)

    def _sc_stack(self, surf, x, z, side, r):
        cols = ((200, 60, 50), (40, 120, 180), (60, 150, 90), (220, 140, 40), (130, 130, 140), (160, 70, 150))
        levels = 2 + int(r * 3)
        for lv in range(levels):
            col = cols[int(r * 97 + lv * 5) % len(cols)]
            vis, front = self.box(surf, x - 1.3, x + 1.3, lv * 2.6, lv * 2.6 + 2.55, z, z + 6.0, col)
            if front:
                for k in range(5):
                    xa = x - 1.1 + k * 0.5
                    self.quad(surf, art.shade(col, 0.75), [(xa, lv * 2.6 + 0.2, z - 0.01), (xa + 0.08, lv * 2.6 + 0.2, z - 0.01),
                                                          (xa + 0.08, lv * 2.6 + 2.35, z - 0.01), (xa, lv * 2.6 + 2.35, z - 0.01)], z)

    def _sc_rack(self, surf, x, z, side, r):
        vis, front = self.box(surf, x - 0.8, x + 0.8, 0, 2.6, z, z + 1.2, (30, 34, 42))
        if front:
            for row in range(6):
                y = 0.3 + row * 0.38
                self.quad(surf, (55, 60, 72), [(x - 0.7, y, z - 0.01), (x + 0.7, y, z - 0.01), (x + 0.7, y + 0.3, z - 0.01), (x - 0.7, y + 0.3, z - 0.01)], z)
                if (int(self.t * 4) + row) % 3:
                    c = ((40, 255, 90), (255, 190, 40), (60, 160, 255))[row % 3]
                    self.quad(surf, c, [(x + 0.45, y + 0.1, z - 0.02), (x + 0.55, y + 0.1, z - 0.02),
                                        (x + 0.55, y + 0.2, z - 0.02), (x + 0.45, y + 0.2, z - 0.02)], z)

    def _sc_codecolumn(self, surf, x, z, side, r):
        """Falling green characters, terminal style."""
        if z < self.near_z():
            return
        s = self.scale_at(z)
        size = int(0.6 * s)
        if size < 9:
            return
        rng = random.Random(int(r * 1e6))
        chars = "01$#{}<>/=;~"
        head = (self.t * (3 + r * 3)) % 10
        for i in range(12):
            y = 8.5 - i * 0.7
            dist = (head - i) % 10
            if dist > 6:
                continue
            g = int(255 * (1 - dist / 6))
            col = (180, 255, 200) if dist < 0.7 else (0, max(60, g), 40)
            ch = chars[(rng.randrange(len(chars)) + int(self.t * 5)) % len(chars)] if dist < 0.7 else chars[rng.randrange(len(chars))]
            img = self._text_img(ch, size, col)
            px, py = self.proj(x, y, z)
            surf.blit(img, img.get_rect(center=(px, py)))

    def _sc_termwindow(self, surf, x, z, side, r):
        if z < self.near_z():
            return
        w, y0, y1 = 2.4, 1.5, 4.5
        self.quad(surf, (0, 60, 25), [(x - w, y0, z), (x + w, y0, z), (x + w, y1, z), (x - w, y1, z)], z)
        self.quad(surf, (0, 12, 5), [(x - w + 0.1, y0 + 0.1, z), (x + w - 0.1, y0 + 0.1, z), (x + w - 0.1, y1 - 0.35, z), (x - w + 0.1, y1 - 0.35, z)], z)
        s = self.scale_at(z)
        size = int(0.32 * s)
        if size >= 7:
            lines = ("$ uname -a", "Linux tux 6.x", "$ ./run --fast", "[ OK ] fish found", "$ _")
            for i, line in enumerate(lines[: 1 + int(self.t * 2 + r * 5) % len(lines)]):
                img = self._text_img(line, size, (80, 255, 120))
                px, py = self.proj(x - w + 0.25, y1 - 0.6 - i * 0.48, z)
                surf.blit(img, (px, py - img.get_height() / 2))

    def _finish(self, surf, z):
        if z < self.near_z():
            return
        col = (240, 240, 245)
        for px in (-4.1, 4.1):
            self.box(surf, px - 0.25, px + 0.25, 0, 6.0, z, z + 0.5, col)
        self.box(surf, -4.3, 4.3, 5.2, 6.4, z, z + 0.4, (40, 160, 80))
        # checkered strip
        for i in range(12):
            x0 = -4.3 + i * (8.6 / 12)
            colr = (20, 20, 20) if i % 2 else (250, 250, 250)
            self.quad(surf, colr, [(x0, 5.2, z - 0.01), (x0 + 8.6 / 12, 5.2, z - 0.01),
                                   (x0 + 8.6 / 12, 5.45, z - 0.01), (x0, 5.45, z - 0.01)], z)
        text = getattr(self, "finish_text", "SAFE")
        s = self.scale_at(z)
        size = int(0.85 * s)
        if 6 < size < 400:
            font = getattr(self, "font_func", _font)(size)
            img = font.render(text, True, (255, 255, 255))
            sx, sy = self.proj(0, 5.95, z - 0.02)
            surf.blit(img, img.get_rect(center=(sx, sy)))

    # ------------------------------------------------------------------ dynamic objects
    def _collect_objects(self, items, world: World):
        far = self.cam_z + C.VIEW_DISTANCE
        nz = self.near_z()
        for o in world.obstacles:
            if o.z > far or o.z1 < nz:
                continue
            fn = {"train": self._train, "ramp": self._ramp, "low": self._low,
                  "high": self._high, "zombie": self._zombie}[o.kind]
            items.append((o.z1, abs(o.x - self.cam_x), fn, (o, world)))
        for f in world.pickups:
            if nz + 0.3 < f.z < self.cam_z + C.VIEW_DISTANCE * 0.85:
                items.append((f.z, abs(f.x - self.cam_x), self._pickup_draw, (f,)))
        for u in world.powerups:
            if nz + 0.3 < u.z < far:
                items.append((u.z, abs(u.x - self.cam_x), self._powerup_draw, (u,)))
        p = world.player
        items.append((p.z + 0.36, abs(p.x - self.cam_x), self._tux, (world,)))
        if world.thief_dist < 10:
            tz = p.z - world.thief_dist
            if tz > nz + 0.5:
                items.append((tz, 0, self._chaser, (world,)))

    def _train(self, surf, o, world):
        th = self.theme
        lx = o.x
        x0, x1 = lx - C.TRAIN_WIDTH / 2, lx + C.TRAIN_WIDTH / 2
        body = th.train_colors[o.color % len(th.train_colors)]
        if th.night and th.key != "terminal":
            body = art.shade(body, 0.75)
        nz = self.near_z()
        for i in reversed(range(o.cars)):
            cz0 = o.z + i * (C.CAR_LENGTH + C.CAR_GAP)
            cz1 = cz0 + C.CAR_LENGTH
            if cz1 < nz:
                continue
            self.box(surf, x0 + 0.25, x1 - 0.25, 0, 0.4, cz0 + 0.5, cz1 - 0.5, (40, 40, 48))
            vis, front = self.box(surf, x0, x1, 0.4, o.height - 0.12, cz0, cz1, body)
            self.box(surf, x0 + 0.08, x1 - 0.08, o.height - 0.12, o.height, cz0 + 0.1, cz1 - 0.1, (190, 195, 205))
            if vis:
                sx = x0 if vis == "l" else x1
                if th.key == "terminal":
                    win = (60, 255, 120)
                else:
                    win = (255, 225, 140) if th.night else (40, 60, 90)
                z = cz0 + 1.0
                while z + 1.4 < cz1:
                    if z + 1.4 > nz:
                        za = max(z, nz)
                        self.quad(surf, win, [(sx, 1.35, za), (sx, 1.95, za), (sx, 1.95, z + 1.4), (sx, 1.35, z + 1.4)])
                    z += 2.2
                za = max(cz0, nz)
                stripe = (60, 255, 120) if th.key == "terminal" else (245, 245, 245)
                self.quad(surf, stripe, [(sx, 0.8, za), (sx, 0.95, za), (sx, 0.95, cz1), (sx, 0.8, cz1)])
            if front:
                self._train_front(surf, o, x0, x1, cz0, body, first=(i == 0))

    def _train_front(self, surf, o, x0, x1, z, body, first):
        zf = z - 0.01
        glass = (60, 90, 130) if not self.theme.night else (25, 35, 60)
        self.quad(surf, glass, [(x0 + 0.25, 1.4, zf), (x1 - 0.25, 1.4, zf), (x1 - 0.25, 2.05, zf), (x0 + 0.25, 2.05, zf)], z)
        self.quad(surf, (210, 230, 250), [(x0 + 0.35, 1.9, zf), (x0 + 0.9, 1.9, zf), (x0 + 0.6, 2.0, zf), (x0 + 0.35, 2.0, zf)], z)
        if not first:
            return
        moving = o.vz < 0
        lamp = (255, 250, 200) if moving else (150, 150, 140)
        for lxp in (x0 + 0.4, x1 - 0.4):
            pts = [(lxp + math.cos(a) * 0.17, 0.85 + math.sin(a) * 0.17, zf) for a in
                   [k * math.tau / 14 for k in range(14)]]
            self.quad(surf, lamp, pts, z)
            if moving:
                flick = 1.6 + 0.2 * math.sin(self.t * 20)
                self.glow(surf, lxp, 0.85, zf - 0.05, flick, (150, 140, 90))
        n = 8
        for k in range(0, n, 2):
            xa = x0 + (x1 - x0) * k / n
            xb = x0 + (x1 - x0) * (k + 1) / n
            self.quad(surf, (250, 200, 40), [(xa, 0.42, zf), (xb, 0.42, zf), (xb, 0.6, zf), (xa, 0.6, zf)], z)

    def _ramp(self, surf, o, world):
        lx = o.x
        x0, x1 = lx - 1.05, lx + 1.05
        nz = self.near_z()
        if o.z1 < nz:
            return
        z0 = max(o.z, nz)
        h0 = o.surface(z0)
        col = (150, 155, 165) if self.theme.key != "terminal" else (0, 90, 40)
        side_x = x0 if self.cam_x < x0 else x1 if self.cam_x > x1 else None
        if side_x is not None:
            self.quad(surf, art.shade(col, 0.7), [(side_x, 0, z0), (side_x, h0, z0), (side_x, o.height, o.z1),
                                                   (side_x, 0, o.z1)])
        self.quad(surf, col, [(x0, h0, z0), (x1, h0, z0), (x1, o.height, o.z1), (x0, o.height, o.z1)])
        z = o.z + 0.5
        while z < o.z1 - 0.3:
            if z > nz:
                ya, yb = o.surface(z), o.surface(z + 0.3)
                self.quad(surf, (240, 190, 40), [(x0, ya + 0.01, z), (x1, ya + 0.01, z), (x1, yb + 0.01, z + 0.3),
                                                 (x0, yb + 0.01, z + 0.3)])
            z += 1.0

    def _low(self, surf, o, world):
        """Firewall: a low brick wall with flames on top. Jump over it!"""
        lx = o.x
        z = o.z
        h = o.height - 0.25
        brick = (175, 55, 40)
        mortar = (120, 40, 30)
        if o.hit:
            for k in range(5):
                bx = lx - 1.0 + k * 0.45
                self.box(surf, bx, bx + 0.35, 0, 0.18, z + (k % 2) * 0.4, z + (k % 2) * 0.4 + 0.25, brick)
            return
        vis, front = self.box(surf, lx - 1.05, lx + 1.05, 0, h, z, z + 0.3, brick, top=mortar)
        if front:
            zf = z - 0.01
            rows = 4
            for rrow in range(1, rows):
                y = h * rrow / rows
                self.quad(surf, mortar, [(lx - 1.05, y - 0.02, zf), (lx + 1.05, y - 0.02, zf), (lx + 1.05, y + 0.02, zf), (lx - 1.05, y + 0.02, zf)], z)
            for rrow in range(rows):
                off = 0.0 if rrow % 2 == 0 else 0.26
                y0, y1 = h * rrow / rows, h * (rrow + 1) / rows
                bx = lx - 1.05 + off + 0.52
                while bx < lx + 1.05:
                    self.quad(surf, mortar, [(bx - 0.02, y0, zf), (bx + 0.02, y0, zf), (bx + 0.02, y1, zf), (bx - 0.02, y1, zf)], z)
                    bx += 0.52
        if z > self.near_z():
            # flames
            n = 6
            for k in range(n):
                fx = lx - 0.95 + k * (1.9 / (n - 1))
                fh = 0.35 + 0.18 * math.sin(self.t * 12 + k * 1.7) + 0.08 * math.sin(self.t * 23 + k)
                self.quad(surf, (255, 120, 20), [(fx - 0.2, h, z + 0.15), (fx + 0.2, h, z + 0.15), (fx, h + fh, z + 0.15)], z)
                self.quad(surf, (255, 220, 60), [(fx - 0.1, h, z + 0.14), (fx + 0.1, h, z + 0.14), (fx, h + fh * 0.6, z + 0.14)], z)
            self.glow(surf, lx, h + 0.2, z, 1.0, (255, 110, 20))

    def _high(self, surf, o, world):
        """Hanging network cables between two poles. Duck or roll under them!"""
        lx = o.x
        z = o.z
        post = (90, 95, 110)
        top = C.HIGH_BARRIER_TOP
        for px in (lx - 1.18, lx + 1.18):
            self.box(surf, px - 0.08, px + 0.08, 0, top, z + 0.1, z + 0.26, post)
        if o.hit or z < self.near_z():
            return
        colors = ((40, 120, 230), (240, 200, 40), (230, 60, 60), (60, 200, 90), (240, 240, 240))
        n = 14
        for ci, col in enumerate(colors):
            sag = 1.45 - ci * 0.12 + 0.05 * math.sin(self.t * 2 + ci)
            y_anchor = top - 0.2 - ci * 0.12
            pts_top, pts_bot = [], []
            for k in range(n + 1):
                f = k / n
                x = lx - 1.12 + 2.24 * f
                lowest = C.HIGH_BARRIER_BOTTOM + 0.1 + ci * 0.09 + 0.04 * sag
                y = y_anchor - (y_anchor - lowest) * 4 * f * (1 - f)
                pts_top.append((x, y + 0.06, z + 0.18))
                pts_bot.append((x, y - 0.06, z + 0.18))
            self.quad(surf, col, pts_top + pts_bot[::-1], z)
        # warning tag
        zf = z + 0.15
        self.quad(surf, (250, 200, 40), [(lx - 0.3, 1.2, zf), (lx + 0.3, 1.2, zf), (lx + 0.3, 1.55, zf), (lx - 0.3, 1.55, zf)], z)
        self.quad(surf, (25, 25, 25), [(lx - 0.15, 1.5, zf - 0.01), (lx + 0.15, 1.5, zf - 0.01), (lx, 1.27, zf - 0.01)], z)

    def _zombie(self, surf, o, world):
        if o.z < self.near_z() + 0.5:
            return
        s = self.scale_at(o.z)
        s_q = max(8, int(s) // 6 * 6)
        phase_q = int(self.t * 8) % 16
        if o.hit:
            phase_q = 0
        img, anchor = self._sprite_cached(("zombie", s_q, phase_q, o.hit),
                                          lambda: art.zombie_front(s_q, phase_q / 4.0))
        if o.hit:
            img = pygame.transform.rotate(img, 75 if o.vx > 0 else -75)
            img.set_alpha(150)
        if o.vx < 0 and not o.hit:
            img = pygame.transform.flip(img, True, False)
            anchor = (img.get_width() - anchor[0], anchor[1])
        fx, fy = self.proj(o.x, 0, o.z)
        surf.blit(img, (fx - anchor[0], fy - anchor[1]))

    def _pickup_draw(self, surf, f):
        s = self.scale_at(f.z)
        bob = math.sin(self.t * 4 + f.z) * 0.08
        w = int((1.0 if f.kind == "key" else 0.9) * s) // 3 * 3
        if w < 4:
            return
        spin = math.cos(self.t * 3 + f.z * 0.2)
        frame = int((spin + 1) * 4)  # 0..8
        key = (w, frame, f.kind)
        img = self._fish.get(key)
        if img is None:
            if len(self._fish) > 800:
                self._fish.clear()
            base = self._fish.get((w, "base", f.kind))
            if base is None:
                base = art.pickup_surface(f.kind, w)
                self._fish[(w, "base", f.kind)] = base
            sx = abs(frame / 4 - 1)
            img = pygame.transform.smoothscale(base, (max(2, int(base.get_width() * max(0.12, sx))), base.get_height()))
            if frame < 4:
                img = pygame.transform.flip(img, True, False)
            self._fish[key] = img
        px, py = self.proj(f.x, f.y + bob, f.z)
        if f.kind != "fish":
            self.glow(surf, f.x, f.y + bob, f.z, 0.8, (90, 70, 10) if f.kind == "golden" else (20, 80, 30))
        surf.blit(img, img.get_rect(center=(px, py)))

    def _powerup_draw(self, surf, u):
        s = self.scale_at(u.z)
        size = int(1.2 * s) // 4 * 4
        if size < 6:
            return
        key = (u.kind, size)
        img = self._pu.get(key)
        if img is None:
            if len(self._pu) > 200:
                self._pu.clear()
            img = art.powerup_surface(u.kind, size)
            self._pu[key] = img
        bob = math.sin(self.t * 3 + u.z) * 0.12
        px, py = self.proj(u.x, u.y + bob, u.z)
        surf.blit(img, img.get_rect(center=(px, py)))

    def _sprite_cached(self, key, factory):
        img = self._sprite.get(key)
        if img is None:
            if len(self._sprite) > 500:
                self._sprite.clear()
            img = factory()
            self._sprite[key] = img
        return img

    def _tux(self, surf, world: World):
        p = world.player
        s = self.scale_at(p.z)
        g = world.support_height(p.x, p.z, p.y + 0.01)
        sx, sy = self.proj(p.x, g, p.z)
        sw = int(1.0 * s * (1.0 - min(0.6, (p.y - g) * 0.12)))
        if sw > 4:
            sh = pygame.Surface((sw, max(2, sw // 3)), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (0, 0, 0, 70), sh.get_rect())
            surf.blit(sh, sh.get_rect(center=(sx, sy)))
        if world.invuln > 0 and int(self.t * 12) % 2 == 0:
            return
        if world.state == "caught":
            mode = "caught"
        elif world.jetpacking:
            mode = "fly"
        elif p.sliding:
            mode = "slide"
        elif p.ducking:
            mode = {"squash": "duck", "roll": "roll", "belly": "belly"}[p.duck_style]
        elif not p.grounded:
            mode = "jump"
        else:
            mode = "run"
        look = 0.0
        if world.stumble_timer > 0 or world.state == "caught":
            look = 1.0 if p.x <= 0 else -1.0
        phase_q = int(p.run_phase * 4) % 16
        tq = int(self.t * 20) % 16 if mode in ("slide", "jump", "caught", "fly") else phase_q
        if mode == "roll":
            phase_q = int(self.t * 24) % 16
            tq = phase_q
        s_q = max(8, int(s) // 4 * 4)
        skin = getattr(self, "skin", "classic")
        board = world.board
        jet = world.jetpacking
        key = ("tux", skin, mode, phase_q, tq, s_q, int(look * 4), board, jet)
        img, anchor = self._sprite_cached(key, lambda: art.tux_back(
            s_q, mode, phase_q / 4.0, tq / 20.0, look, skin=skin, board=board, jet=jet))
        fx, fy = self.proj(p.x, p.y, p.z)
        if board:
            fy -= 0.12 * s
        if p.stumble_anim > 0 or mode == "slide":
            ang = math.sin(self.t * 25) * 8 * (p.stumble_anim * 2 if p.stumble_anim > 0 else 0.8)
            rot = pygame.transform.rotate(img, ang)
            cx = fx - anchor[0] + img.get_width() / 2
            cy = fy - anchor[1] + img.get_height() / 2
            surf.blit(rot, rot.get_rect(center=(cx, cy)))
        else:
            surf.blit(img, (fx - anchor[0], fy - anchor[1]))
        if world.magnet_t > 0:
            r = int((1.1 + 0.1 * math.sin(self.t * 10)) * s)
            ring = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 90, 90, 90), (r, r), r, max(2, int(3 * self.u)))
            bx, by = self.proj(p.x, p.y + 0.75, p.z)
            surf.blit(ring, ring.get_rect(center=(bx, by)))
        if jet and self.t % 0.05 < 0.025:
            self.burst(p.x + random.uniform(-0.3, 0.3), p.y + 0.3, p.z - 0.2, (255, 170, 60), n=2, speed=1.5,
                       size=0.1, life=0.35, gravity=-2)

    def _chaser(self, surf, world: World):
        p = world.player
        z = p.z - world.thief_dist
        side = -1 if p.x > 0.1 else 1
        off = 1.35 if world.state != "caught" else max(0.5, 1.35 - world.end_time * 2)
        x = p.x + side * off
        s = self.scale_at(z)
        phase_q = int(p.run_phase * 2) % 8
        grab = world.state == "caught" or world.thief_dist < 3.0
        tq = int(self.t * 8) % 4
        kind = world.chaser
        # draw once at a reference scale, then only rescale (drawing at full size is slow)
        ref = max(40, int(160 * self.u))
        base, banchor = self._sprite_cached(("chaser", kind, ref, phase_q, grab, tq),
                                            lambda: art.chaser_back(kind, ref, phase_q / 2.0, tq / 8.0, grab))
        size_q = max(8, int(s) // 12 * 12)
        f = size_q / ref

        def scaled():
            w, h = base.get_size()
            return pygame.transform.smoothscale(base, (max(1, int(w * f)), max(1, int(h * f)))), \
                (banchor[0] * f, banchor[1] * f)

        img, anchor = self._sprite_cached(("chaser_s", kind, size_q, phase_q, grab, tq), scaled)
        fx, fy = self.proj(x, 0, z)
        surf.blit(img, (fx - anchor[0], fy - anchor[1]))

    # ------------------------------------------------------------------ particles & weather
    def burst(self, x, y, z, color, n=10, speed=3.0, size=0.08, life=0.5, gravity=8.0):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            v = random.uniform(0.3, 1.0) * speed
            self.particles.append(Particle(x, y, z, math.cos(a) * v, random.uniform(0.5, 1.5) * speed,
                                           math.sin(a) * v, life * random.uniform(0.6, 1.2), color, size, gravity))

    def _draw_particles(self, surf, dt):
        alive = []
        nz = self.near_z()
        for pt in self.particles:
            pt.life -= dt
            if pt.life <= 0:
                continue
            pt.vy -= pt.gravity * dt
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            pt.z += pt.vz * dt
            alive.append(pt)
            if pt.z < nz:
                continue
            px, py = self.proj(pt.x, pt.y, pt.z)
            r = int(pt.size * self.scale_at(pt.z) * (pt.life / pt.max_life) ** 0.5)
            if r >= 1:
                pygame.draw.circle(surf, pt.color, (int(px), int(py)), r)
        self.particles = alive[-400:]

    def _draw_snow(self, surf, amount, dt, speed):
        n = int(len(self.snow) * amount)
        col = (255, 255, 255)
        for flake in self.snow[:n]:
            flake[1] += (60 + speed * 6) * flake[2] * dt * self.u
            flake[0] += (math.sin(self.t + flake[2] * 10) * 30 - (flake[0] - self.cx) * 0.4) * dt * self.u
            if flake[1] > self.H or flake[0] < 0 or flake[0] > self.W:
                flake[0] = random.random() * self.W
                flake[1] = random.uniform(-20, self.horizon)
            pygame.draw.circle(surf, col, (int(flake[0]), int(flake[1])), max(1, int(3 * flake[2] * self.u)))

    def _vignette(self, surf, strength):
        key = ("vig", strength)
        v = self._glow.get(key)
        if v is None:
            v = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            steps = 24
            for i in range(steps):
                a = int(strength * (1 - i / steps) ** 2)
                rect = pygame.Rect(0, 0, self.W, self.H).inflate(-i * self.W // (steps * 2), -i * self.H // (steps * 2))
                pygame.draw.rect(v, (0, 0, 10, a), rect, max(1, self.W // (steps * 4)))
            self._glow[key] = v
        surf.blit(v, (0, 0))


_FONTS: dict = {}


def _font(size):
    f = _FONTS.get(size)
    if f is None:
        f = pygame.font.Font(None, size)
        _FONTS[size] = f
    return f
