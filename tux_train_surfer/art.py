"""Procedural artwork. Every image in the game is drawn here with code, so the
whole game - graphics included - is free software under the project licence.
"""

from __future__ import annotations

import math
import random

import pygame
import pygame.gfxdraw

SS = 2  # supersampling factor for smooth edges

BLACK = (22, 24, 30)
BLACK_HI = (55, 60, 72)
WHITE = (248, 248, 252)
ORANGE = (250, 165, 30)
ORANGE_DARK = (215, 120, 20)

SKINS = (
    # key, fish needed to unlock
    ("classic", 0),
    ("winter", 150),
    ("sysadmin", 400),
    ("retro", 800),
    ("captain", 1500),
)

SCARF_COLORS = {
    "classic": ((215, 40, 50), (160, 25, 35)),
    "winter": ((40, 150, 80), (25, 100, 55)),
    "sysadmin": ((60, 70, 90), (40, 45, 60)),
    "retro": ((255, 60, 180), (40, 220, 210)),
    "captain": ((30, 60, 140), (20, 40, 100)),
}


# --------------------------------------------------------------------------- primitives
def _ipts(pts):
    return [(int(round(x)), int(round(y))) for x, y in pts]


def fill_poly(surf, color, pts) -> None:
    if len(pts) < 3:
        return
    p = _ipts(pts)
    pygame.gfxdraw.filled_polygon(surf, p, color)
    pygame.gfxdraw.aapolygon(surf, p, color)


def ellipse_pts(cx, cy, rx, ry, angle=0.0, n=36, a0=0.0, a1=math.tau):
    ca, sa = math.cos(angle), math.sin(angle)
    pts = []
    for i in range(n + 1):
        t = a0 + (a1 - a0) * i / n
        x, y = math.cos(t) * rx, math.sin(t) * ry
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return pts


def fill_ellipse(surf, color, cx, cy, rx, ry, angle=0.0, n=36) -> None:
    fill_poly(surf, color, ellipse_pts(cx, cy, rx, ry, angle, n))


def thick_line(surf, color, a, b, w) -> None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d * w / 2, dx / d * w / 2
    fill_poly(surf, color, [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny),
                            (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)])
    fill_ellipse(surf, color, a[0], a[1], w / 2, w / 2, n=16)
    fill_ellipse(surf, color, b[0], b[1], w / 2, w / 2, n=16)


def shade(color, f):
    return tuple(max(0, min(255, int(c * f))) for c in color[:3])


def lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Canvas:
    """A supersampled drawing area in metres with the origin at the feet."""

    def __init__(self, px_per_m: float, width_m: float, height_m: float, foot_m: float = 0.15):
        self.k = max(1.0, px_per_m * SS)
        self.w = max(2, int(width_m * self.k))
        self.h = max(2, int(height_m * self.k))
        self.ox = self.w / 2
        self.oy = self.h - foot_m * self.k
        self.surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)

    def p(self, x, y):
        return (self.ox + x * self.k, self.oy - y * self.k)

    def ellipse(self, color, x, y, rx, ry, angle_deg=0.0):
        cx, cy = self.p(x, y)
        fill_ellipse(self.surf, color, cx, cy, rx * self.k, ry * self.k, -math.radians(angle_deg))

    def poly(self, color, pts):
        fill_poly(self.surf, color, [self.p(x, y) for x, y in pts])

    def line(self, color, a, b, w):
        thick_line(self.surf, color, self.p(*a), self.p(*b), w * self.k)

    def rect(self, color, x0, y0, x1, y1):
        self.poly(color, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    def result(self):
        out = pygame.transform.smoothscale(self.surf, (max(1, self.w // SS), max(1, self.h // SS)))
        return out, (self.ox / SS, self.oy / SS)


# --------------------------------------------------------------------------- Tux pieces
def _flipper(cv, side, sx, sy, angle_deg, length=0.3, color=BLACK):
    a = math.radians(angle_deg) * side
    cx = sx + math.sin(a) * length * 0.9
    cy = sy - math.cos(a) * length * 0.9
    cv.ellipse(color, cx, cy, 0.085, length, -math.degrees(a))


def _scarf_tail(cv, x, y, t, color, up=False):
    pts_top, pts_bot = [], []
    for i in range(7):
        wave = math.sin(t * 15 - i * 0.9) * 0.045 * (i / 6)
        px = x + i * 0.075
        py = y - (i * 0.035 if not up else -i * 0.03) + wave
        pts_top.append((px, py + 0.045))
        pts_bot.append((px, py - 0.045))
    cv.poly(color, pts_top + pts_bot[::-1])


def _face_side(cv, look, hx, hy, skin):
    s = 1 if look > 0 else -1
    a = min(1.0, abs(look))
    ex = hx + s * 0.15 * a
    if skin == "retro":
        cv.poly((20, 20, 20), [(ex - 0.1, hy + 0.13), (ex + 0.12, hy + 0.13), (ex + 0.1, hy), (ex - 0.08, hy)])
        cv.line((255, 60, 180), (ex - 0.1, hy + 0.13), (ex + 0.12, hy + 0.13), 0.02)
    else:
        cv.ellipse(WHITE, ex, hy + 0.05, 0.05 + 0.04 * a, 0.1)
        cv.ellipse(BLACK, ex + s * 0.03 * a, hy + 0.04, 0.03, 0.045)
        cv.line(BLACK, (ex - s * 0.08, hy + 0.2), (ex + s * 0.08, hy + 0.13), 0.045)
    bx = hx + s * (0.2 + 0.08 * a)
    cv.poly(ORANGE, [(bx - s * 0.06, hy - 0.02), (bx - s * 0.06, hy - 0.12),
                     (bx + s * (0.1 + 0.08 * a), hy - 0.08)])


def _hat_back(cv, skin, hx, hy, r, t):
    """Head-wear seen from behind, drawn over the head."""
    if skin == "winter":
        cv.poly((40, 150, 80), [(hx - r * 1.02, hy + r * 0.25)] +
                [(hx + math.cos(a) * r * 1.02, hy + math.sin(a) * r * 1.05) for a in
                 [math.pi * i / 12 for i in range(13)]][::-1] + [(hx + r * 1.02, hy + r * 0.25)])
        for i in range(3):
            yy = hy + r * (0.42 + i * 0.2)
            hw = r * math.sqrt(max(0.0, 1 - ((yy - hy) / (r * 1.05)) ** 2))
            cv.rect(WHITE, hx - hw, yy, hx + hw, yy + r * 0.08)
        cv.rect((230, 230, 235), hx - r * 1.05, hy + r * 0.1, hx + r * 1.05, hy + r * 0.32)
        cv.ellipse(WHITE, hx + math.sin(t * 9) * 0.03, hy + r * 1.15, r * 0.3, r * 0.3)
    elif skin == "sysadmin":
        cv.line((50, 50, 55), (hx - r * 0.98, hy + r * 0.1), (hx - r * 0.5, hy + r * 0.92), 0.06)
        cv.line((50, 50, 55), (hx - r * 0.5, hy + r * 0.92), (hx + r * 0.5, hy + r * 0.92), 0.06)
        cv.line((50, 50, 55), (hx + r * 0.5, hy + r * 0.92), (hx + r * 0.98, hy + r * 0.1), 0.06)
        for s in (-1, 1):
            cv.ellipse((70, 70, 80), hx + s * r * 1.0, hy, r * 0.22, r * 0.32)
            cv.ellipse((40, 200, 90), hx + s * r * 1.05, hy, r * 0.06, r * 0.08)
    elif skin == "retro":
        cv.ellipse((120, 50, 200), hx, hy + r * 0.45, r * 1.02, r * 0.62)
        cv.rect((120, 50, 200), hx - r * 1.02, hy + r * 0.2, hx + r * 1.02, hy + r * 0.45)
        cv.poly((40, 230, 210), [(hx - r * 0.6, hy + r * 0.22), (hx + r * 0.6, hy + r * 0.22),
                                 (hx + r * 0.45, hy - r * 0.15), (hx - r * 0.45, hy - r * 0.15)])
        cv.rect((255, 60, 180), hx - r * 0.25, hy + r * 0.22, hx + r * 0.25, hy + r * 0.32)
    elif skin == "captain":
        cv.ellipse(WHITE, hx, hy + r * 0.75, r * 1.2, r * 0.38)
        cv.rect((20, 20, 30), hx - r * 1.0, hy + r * 0.32, hx + r * 1.0, hy + r * 0.62)
        cv.rect((230, 180, 40), hx - r * 1.0, hy + r * 0.5, hx + r * 1.0, hy + r * 0.58)


def _body_back_extras(cv, skin, bob, jet, t):
    if skin == "sysadmin":
        cv.line((40, 110, 220), (-0.2, 1.0 + bob), (-0.05, 0.55 + bob), 0.04)
        cv.line((40, 110, 220), (0.2, 1.0 + bob), (0.05, 0.55 + bob), 0.04)
        cv.rect((60, 62, 70), -0.25, 0.45 + bob, 0.25, 0.88 + bob)
        cv.rect((80, 82, 92), -0.22, 0.48 + bob, 0.22, 0.85 + bob)
        cv.ellipse((255, 200, 40), -0.08, 0.7 + bob, 0.06, 0.06)   # a sticker, of course
        cv.ellipse((40, 200, 90), 0.1, 0.62 + bob, 0.05, 0.05)
    elif skin == "retro":
        cv.rect((255, 60, 180), -0.4, 0.35 + bob, 0.4, 0.43 + bob)
        cv.ellipse((40, 230, 210), 0, 0.4 + bob, 0.2, 0.11)
        cv.ellipse((255, 240, 60), 0, 0.41 + bob, 0.06, 0.04)
    elif skin == "captain":
        cv.poly((30, 60, 140), [(-0.33, 1.02 + bob), (0.33, 1.02 + bob), (0.3, 0.68 + bob), (-0.3, 0.68 + bob)])
        for k in (0.73, 0.79):
            cv.rect(WHITE, -0.27, k + bob, 0.27, k + 0.025 + bob)
    if jet:
        for s in (-1, 1):
            cv.rect((150, 155, 170), s * 0.25 - 0.1, 0.5 + bob, s * 0.25 + 0.1, 1.0 + bob)
            cv.ellipse((190, 195, 210), s * 0.25, 1.0 + bob, 0.1, 0.04)
            fl = 0.28 + 0.08 * math.sin(t * 40 + s)
            cv.poly((255, 150, 30), [(s * 0.25 - 0.09, 0.5 + bob), (s * 0.25 + 0.09, 0.5 + bob),
                                     (s * 0.25, 0.5 + bob - fl)])
            cv.poly((255, 240, 120), [(s * 0.25 - 0.05, 0.5 + bob), (s * 0.25 + 0.05, 0.5 + bob),
                                      (s * 0.25, 0.5 + bob - fl * 0.6)])


def _board(cv, t):
    glow = 0.5 + 0.5 * math.sin(t * 8)
    cv.ellipse((120, 200, 255, 90), 0, -0.04, 0.62, 0.12)
    cv.ellipse((90, 160, 230), 0, 0.0, 0.55, 0.1)
    cv.ellipse((200, 235, 255), 0, 0.03, 0.5, 0.07)
    cv.rect((40, 220, 255, int(120 + 100 * glow)), -0.4, -0.02, 0.4, 0.0)


def tux_back(px_per_m: float, mode: str = "run", phase: float = 0.0, t: float = 0.0,
             look: float = 0.0, skin: str = "classic", board: bool = False, jet: bool = False):
    """Tux seen from behind. Returns (surface, anchor) where anchor is the feet point."""
    cv = Canvas(px_per_m, 2.0, 2.3, foot_m=0.25)
    scarf, scarf2 = SCARF_COLORS.get(skin, SCARF_COLORS["classic"])
    s = math.sin(phase * math.pi)
    if board:
        _board(cv, t)
    if mode in ("slide", "belly"):
        wob = math.sin(t * 11) * 0.04 if mode == "slide" else 0.0
        cv.ellipse(BLACK, 0, 0.55, 0.22, 0.22)
        _hat_back(cv, skin, 0, 0.55, 0.22, t)
        cv.ellipse(scarf, 0, 0.45, 0.25, 0.07)
        _scarf_tail(cv, 0.1, 0.48, t, scarf2, up=True)
        cv.ellipse(WHITE, 0, 0.26, 0.45, 0.25)
        cv.ellipse(BLACK, 0, 0.31, 0.4, 0.27)
        cv.ellipse(BLACK, -0.48, 0.3 + wob, 0.32, 0.08, 12)
        cv.ellipse(BLACK, 0.48, 0.3 - wob, 0.32, 0.08, -12)
        for sx in (-0.15, 0.15):
            cv.ellipse(ORANGE_DARK, sx, 0.08, 0.14, 0.12)
            cv.ellipse(ORANGE, sx, 0.09, 0.11, 0.09)
        return cv.result()

    if mode == "roll":
        a = phase * 2.2
        cv.ellipse(BLACK, 0, 0.4, 0.4, 0.4)
        for k in range(2):
            ang = a + k * math.pi
            cv.ellipse(WHITE, math.cos(ang) * 0.22, 0.4 + math.sin(ang) * 0.22, 0.12, 0.08, math.degrees(ang))
        fa = a + math.pi / 2
        cv.ellipse(ORANGE, math.cos(fa) * 0.3, 0.4 + math.sin(fa) * 0.3, 0.09, 0.06)
        cv.ellipse(ORANGE, math.cos(fa + 0.5) * 0.3, 0.4 + math.sin(fa + 0.5) * 0.3, 0.09, 0.06)
        cv.ellipse(scarf, math.cos(a + 2.5) * 0.3, 0.4 + math.sin(a + 2.5) * 0.3, 0.1, 0.07)
        return cv.result()

    if mode == "duck":
        cv.ellipse(ORANGE, -0.18, 0.05, 0.15, 0.07)
        cv.ellipse(ORANGE, 0.18, 0.05, 0.15, 0.07)
        cv.ellipse(WHITE, 0, 0.33, 0.47, 0.3)
        cv.ellipse(BLACK, 0, 0.38, 0.43, 0.33)
        _flipper(cv, -1, -0.38, 0.5, 115, 0.26)
        _flipper(cv, 1, 0.38, 0.5, 115, 0.26)
        cv.ellipse(scarf, 0, 0.62, 0.27, 0.07)
        _scarf_tail(cv, 0.1, 0.62, t, scarf2)
        cv.ellipse(BLACK, 0, 0.78, 0.26, 0.24)
        _hat_back(cv, skin, 0, 0.78, 0.26, t)
        if abs(look) > 0.05:
            _face_side(cv, look, 0, 0.78, skin)
        return cv.result()

    air = mode in ("jump", "fly")
    bob = 0.0 if air else abs(s) * 0.05
    if air:
        lift_l = lift_r = 0.1
    else:
        lift_l, lift_r = max(0.0, s) * 0.13, max(0.0, -s) * 0.13
    for side, lift in ((-1, lift_l), (1, lift_r)):
        fx = side * 0.17
        cv.ellipse(ORANGE_DARK, fx, 0.06 + lift, 0.15, 0.08 + lift * 0.3)
        cv.ellipse(ORANGE, fx, 0.07 + lift, 0.12, 0.05 + lift * 0.25)
    cv.ellipse(WHITE, 0, 0.55 + bob, 0.42, 0.45)
    cv.ellipse(BLACK, 0, 0.63 + bob, 0.385, 0.5)
    cv.ellipse(BLACK_HI, -0.12, 0.8 + bob, 0.1, 0.22, 15)
    if mode == "fly":
        _flipper(cv, -1, -0.34, 0.9, 95 + math.sin(t * 10) * 8)
        _flipper(cv, 1, 0.34, 0.9, 95 - math.sin(t * 10) * 8)
    elif mode == "jump":
        fa = 120 + math.sin(t * 20) * 10
        _flipper(cv, -1, -0.34, 0.9 + bob, fa)
        _flipper(cv, 1, 0.34, 0.9 + bob, fa)
    elif mode == "caught":
        _flipper(cv, -1, -0.34, 0.9, 150 + math.sin(t * 30) * 15)
        _flipper(cv, 1, 0.34, 0.9, 150 - math.sin(t * 30) * 15)
    else:
        _flipper(cv, -1, -0.34, 0.9 + bob, 25 + 30 * s)
        _flipper(cv, 1, 0.34, 0.9 + bob, 25 - 30 * s)
    _body_back_extras(cv, skin, bob, jet, t)
    cv.ellipse(scarf2, 0, 1.0 + bob, 0.3, 0.085)
    cv.ellipse(scarf, 0, 1.01 + bob, 0.29, 0.07)
    if skin != "captain":
        _scarf_tail(cv, 0.12, 1.0 + bob, t, scarf)
    cv.ellipse(BLACK, 0, 1.24 + bob, 0.3, 0.3)
    cv.ellipse(BLACK_HI, -0.1, 1.33 + bob, 0.08, 0.1)
    if abs(look) > 0.05:
        _face_side(cv, look, 0, 1.24 + bob, skin)
    _hat_back(cv, skin, 0, 1.24 + bob, 0.3, t)
    return cv.result()


# --------------------------------------------------------------------------- Tux (front, menus)
def tux_front(size_px: int, angry: bool = True, wave: float = 0.0, fish: bool = True,
              skin: str = "classic") -> pygame.Surface:
    """A big front-facing Tux for menus and the application icon."""
    cv = Canvas(size_px / 2.2, 2.2, 2.2, foot_m=0.08)
    scarf, scarf2 = SCARF_COLORS.get(skin, SCARF_COLORS["classic"])
    cv.ellipse(ORANGE_DARK, -0.3, 0.1, 0.27, 0.12)
    cv.ellipse(ORANGE_DARK, 0.3, 0.1, 0.27, 0.12)
    cv.ellipse(ORANGE, -0.3, 0.12, 0.24, 0.09)
    cv.ellipse(ORANGE, 0.3, 0.12, 0.24, 0.09)
    cv.ellipse(BLACK, 0, 0.72, 0.62, 0.68)
    cv.ellipse(WHITE, 0, 0.62, 0.45, 0.55)
    if skin == "retro":
        cv.rect((255, 60, 180), -0.55, 0.42, 0.55, 0.5)
        cv.ellipse((40, 230, 210), 0, 0.42, 0.22, 0.12)
    elif skin == "sysadmin":
        cv.line((40, 110, 220), (-0.25, 1.15), (0, 0.75), 0.05)
        cv.line((40, 110, 220), (0.25, 1.15), (0, 0.75), 0.05)
        cv.rect((245, 245, 245), -0.12, 0.5, 0.12, 0.75)
        cv.rect((40, 110, 220), -0.12, 0.68, 0.12, 0.75)
        cv.ellipse((200, 200, 210), 0, 0.6, 0.05, 0.05)
    _flipper(cv, -1, -0.52, 1.0, 35 + wave * 40, 0.42)
    _flipper(cv, 1, 0.52, 1.0, 35, 0.42)
    if skin == "captain":
        cv.poly((30, 60, 140), [(-0.45, 1.2), (0.45, 1.2), (0, 0.85)])
        cv.poly(WHITE, [(-0.3, 1.2), (0.3, 1.2), (0, 0.97)])
        cv.poly((30, 60, 140), [(-0.22, 1.2), (0.22, 1.2), (0, 1.03)])
    else:
        cv.ellipse(scarf2, 0, 1.17, 0.47, 0.11)
        cv.ellipse(scarf, 0, 1.19, 0.45, 0.09)
        cv.poly(scarf, [(0.15, 1.15), (0.33, 1.12), (0.42, 0.78), (0.26, 0.8)])
    cv.ellipse(BLACK, 0, 1.5, 0.45, 0.42)
    for side in (-1, 1):
        if skin == "retro":
            continue
        cv.ellipse(WHITE, side * 0.15, 1.58, 0.12, 0.15)
        cv.ellipse(BLACK, side * 0.12, 1.55, 0.06, 0.08)
        cv.ellipse(WHITE, side * 0.1, 1.58, 0.02, 0.025)
        if angry:
            cv.line(BLACK, (side * 0.28, 1.8), (side * 0.04, 1.69), 0.07)
    if skin == "retro":
        cv.poly((15, 15, 20), [(-0.36, 1.68), (0.36, 1.68), (0.3, 1.5), (0.04, 1.52), (0, 1.58),
                               (-0.04, 1.52), (-0.3, 1.5)])
        cv.line((255, 60, 180), (-0.36, 1.68), (0.36, 1.68), 0.03)
    cv.ellipse(ORANGE_DARK, 0, 1.35, 0.2, 0.09)
    cv.ellipse(ORANGE, 0, 1.38, 0.18, 0.07)
    # hats (front)
    if skin == "winter":
        cv.ellipse((40, 150, 80), 0, 1.78, 0.44, 0.3)
        cv.rect((40, 150, 80), -0.44, 1.7, 0.44, 1.78)
        cv.rect(WHITE, -0.46, 1.66, 0.46, 1.76)
        for i in range(2):
            cv.rect(WHITE, -0.38 + i * 0.06, 1.86 + i * 0.08, 0.38 - i * 0.06, 1.9 + i * 0.08)
        cv.ellipse(WHITE, 0, 2.1, 0.12, 0.12)
    elif skin == "sysadmin":
        cv.line((50, 50, 55), (-0.44, 1.55), (-0.3, 1.88), 0.06)
        cv.line((50, 50, 55), (-0.3, 1.88), (0.3, 1.88), 0.06)
        cv.line((50, 50, 55), (0.3, 1.88), (0.44, 1.55), 0.06)
        for s in (-1, 1):
            cv.ellipse((70, 70, 80), s * 0.46, 1.5, 0.1, 0.14)
        cv.line((50, 50, 55), (-0.46, 1.42), (-0.2, 1.3), 0.03)
        cv.ellipse((50, 50, 55), -0.2, 1.3, 0.04, 0.04)
    elif skin == "retro":
        cv.ellipse((120, 50, 200), 0, 1.82, 0.42, 0.22)
        cv.rect((120, 50, 200), -0.42, 1.74, 0.42, 1.82)
        cv.poly((40, 230, 210), [(-0.25, 1.98), (0.25, 1.98), (0.18, 2.08), (-0.18, 2.08)])
    elif skin == "captain":
        cv.ellipse(WHITE, 0, 1.9, 0.5, 0.17)
        cv.rect(WHITE, -0.4, 1.76, 0.4, 1.9)
        cv.rect((20, 20, 30), -0.42, 1.7, 0.42, 1.78)
        cv.poly((20, 20, 30), [(-0.42, 1.72), (0.42, 1.72), (0.3, 1.62), (-0.3, 1.62)])
        cv.rect((230, 180, 40), -0.4, 1.76, 0.4, 1.8)
        # little anchor
        cv.line((230, 180, 40), (0, 1.93), (0, 1.82), 0.025)
        cv.line((230, 180, 40), (-0.05, 1.84), (0.05, 1.84), 0.02)
        cv.line((230, 180, 40), (-0.04, 1.9), (0.04, 1.9), 0.02)
    if fish:
        f = pickup_surface("fish", int(cv.k * 0.55))
        f = pygame.transform.rotate(f, 25)
        cv.surf.blit(f, f.get_rect(center=cv.p(-0.66, 0.7)))
    out, _ = cv.result()
    return out


# --------------------------------------------------------------------------- chasers (back view)
SKIN_TONE = (235, 190, 160)


def chaser_back(kind: str, px_per_m: float, phase: float = 0.0, t: float = 0.0, grab: bool = False):
    if kind == "kernel":
        return _kernel_back(px_per_m, phase, t, grab)
    if kind == "segfault":
        return _segfault_back(px_per_m, phase, t, grab)
    if kind == "lockin":
        return _lockin_back(px_per_m, phase, t, grab)
    return _thief_back(px_per_m, phase, t, grab)


def _legs(cv, s, color, shoe, top=0.95, spread=0.15):
    for side in (-1, 1):
        lift = max(0.0, s * side) * 0.18
        cv.line(color, (side * spread * 0.9, top), (side * spread, 0.12 + lift), 0.17)
        cv.ellipse(shoe, side * spread, 0.08 + lift, 0.11, 0.08)


def _arms(cv, s, color, shoulder_y, bob, grab, t, glove=(250, 250, 250), w=0.3):
    for side in (-1, 1):
        if grab:
            hand = (side * 0.35, shoulder_y + 0.5 + math.sin(t * 25) * 0.05)
        else:
            hand = (side * (w + 0.15), shoulder_y - 0.5 + bob - s * side * 0.15)
        cv.line(color, (side * w, shoulder_y + bob), hand, 0.13)
        cv.ellipse(glove, hand[0], hand[1], 0.08, 0.08)


def _thief_back(px, phase, t, grab):
    cv = Canvas(px, 1.8, 2.4)
    s = math.sin(phase * math.pi)
    bob = abs(s) * 0.05
    _legs(cv, s, (45, 60, 100), (30, 30, 35))
    sack = (160, 120, 70)
    cv.ellipse(shade(sack, 0.8), 0.38, 1.75 + bob, 0.33, 0.3)
    cv.ellipse(sack, 0.36, 1.77 + bob, 0.3, 0.27)
    top, bot = 1.62 + bob, 0.9 + bob
    cv.poly((245, 245, 245), [(-0.3, bot), (0.3, bot), (0.33, top), (-0.33, top)])
    for i in range(0, 6, 2):
        y0 = bot + (top - bot) * i / 6
        y1 = bot + (top - bot) * (i + 1) / 6
        cv.poly((30, 30, 38), [(-0.31, y0), (0.31, y0), (0.32, y1), (-0.32, y1)])
    _arms(cv, s, (30, 30, 38), 1.55, bob, grab, t)
    cv.ellipse(SKIN_TONE, 0, 1.8 + bob, 0.15, 0.17)
    cv.ellipse((25, 25, 30), 0, 1.88 + bob, 0.17, 0.12)
    cv.poly((25, 25, 30), [(-0.17, 1.86 + bob), (0.17, 1.86 + bob), (0.12, 2.02 + bob), (-0.12, 2.02 + bob)])
    cv.ellipse((25, 25, 30), 0, 2.03 + bob, 0.06, 0.05)
    return cv.result()


def _kernel_back(px, phase, t, grab):
    """Kernel Panic: an angry old CRT monitor on legs, glowing red."""
    cv = Canvas(px, 2.4, 2.8)
    s = math.sin(phase * math.pi)
    bob = abs(s) * 0.05
    pulse = 0.5 + 0.5 * math.sin(t * 9)
    for i in range(4, 0, -1):
        cv.ellipse((255, 40, 30, int(25 + pulse * 25)), 0, 1.5, 0.75 + i * 0.12, 0.8 + i * 0.1)
    _legs(cv, s, (90, 90, 95), (40, 40, 45), top=0.85, spread=0.22)
    beige = (205, 198, 175)
    cv.poly(shade(beige, 0.85), [(-0.65, 0.85 + bob), (0.65, 0.85 + bob), (0.7, 2.15 + bob), (-0.7, 2.15 + bob)])
    cv.poly(beige, [(-0.42, 1.0 + bob), (0.42, 1.0 + bob), (0.45, 1.95 + bob), (-0.45, 1.95 + bob)])
    for k in range(5):
        y = 1.2 + k * 0.14 + bob
        cv.rect(shade(beige, 0.6), -0.3, y, 0.3, y + 0.04)
    # power cable tail
    pts = [(0.0, 1.0 + bob)]
    for k in range(1, 7):
        pts.append((math.sin(t * 6 + k) * 0.12 + k * 0.06, 1.0 - k * 0.12 + bob))
    for a, b in zip(pts, pts[1:]):
        cv.line((30, 30, 30), a, b, 0.05)
    _arms(cv, s, (90, 90, 95), 1.75, bob, grab, t, glove=(255, 80, 60), w=0.68)
    # little red error lights
    for k in range(3):
        on = (int(t * 6) + k) % 3 == 0
        cv.ellipse((255, 40, 30) if on else (90, 20, 20), -0.5 + k * 0.08, 2.05 + bob, 0.03, 0.03)
    return cv.result()


def _segfault_back(px, phase, t, grab):
    """Segfault Monster: a jagged glitchy purple blob."""
    cv = Canvas(px, 2.4, 2.8)
    s = math.sin(phase * math.pi)
    bob = abs(s) * 0.08
    rng = random.Random(int(t * 12))
    _legs(cv, s, (90, 40, 130), (50, 20, 70), top=0.7, spread=0.25)
    pts = []
    n = 18
    for i in range(n):
        a = i * math.tau / n
        r = 0.72 + (0.22 if i % 2 == 0 else 0.0) + rng.uniform(-0.03, 0.03)
        pts.append((math.cos(a) * r * 0.95, 1.45 + bob + math.sin(a) * r))
    cv.poly((120, 50, 170), pts)
    cv.ellipse((150, 80, 200), -0.15, 1.6 + bob, 0.4, 0.45)
    for _ in range(7):
        x = rng.uniform(-0.8, 0.8)
        y = rng.uniform(0.9, 2.1) + bob
        w = rng.uniform(0.06, 0.25)
        col = rng.choice(((255, 60, 200), (60, 255, 230), (255, 255, 255), (30, 0, 40)))
        cv.rect(col, x, y, x + w, y + 0.05)
    for side in (-1, 1):
        cv.poly((70, 20, 100), [(side * 0.3, 2.1 + bob), (side * 0.5, 2.55 + bob), (side * 0.55, 2.05 + bob)])
    _arms(cv, s, (110, 45, 160), 1.6, bob, grab, t, glove=(70, 20, 100), w=0.7)
    return cv.result()


def _lockin_back(px, phase, t, grab):
    """Proprietary Lock-in: a huge golden padlock with chain arms."""
    cv = Canvas(px, 2.4, 3.0)
    s = math.sin(phase * math.pi)
    bob = abs(s) * 0.05
    _legs(cv, s, (110, 110, 120), (60, 60, 70), top=0.85, spread=0.22)
    # shackle
    outer = ellipse_pts(0, 0, 0.42, 0.5, 0, 20, 0, math.pi)
    inner = ellipse_pts(0, 0, 0.27, 0.36, 0, 20, 0, math.pi)
    base_y = 2.0 + bob
    o = [(x, base_y + y) for x, y in outer]
    i = [(x, base_y + y) for x, y in inner][::-1]
    cv.poly((175, 180, 195), o + [(-0.42, base_y), (-0.27, base_y)] + i + [(0.27, base_y)])
    gold = (230, 180, 40)
    cv.poly(shade(gold, 0.75), [(-0.62, 0.85 + bob), (0.62, 0.85 + bob), (0.62, 2.05 + bob), (-0.62, 2.05 + bob)])
    cv.poly(gold, [(-0.55, 0.92 + bob), (0.55, 0.92 + bob), (0.55, 1.98 + bob), (-0.55, 1.98 + bob)])
    cv.rect(shade(gold, 1.2), -0.5, 1.75 + bob, 0.5, 1.85 + bob)
    for side in (-1, 1):
        if grab:
            hand = (side * 0.4, 2.3 + math.sin(t * 25) * 0.05)
        else:
            hand = (side * 0.8, 1.0 + bob - s * side * 0.15)
        sx, sy = side * 0.6, 1.7 + bob
        for k in range(5):
            f = k / 4
            cx = sx + (hand[0] - sx) * f
            cy = sy + (hand[1] - sy) * f
            cv.ellipse((150, 150, 160), cx, cy, 0.07, 0.05, 90 * (k % 2))
    return cv.result()


def chaser_front(kind: str, size_px: int) -> pygame.Surface:
    """Small portrait used in the HUD and menus."""
    S = max(16, size_px) * SS
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2

    def eyes(y, col=(255, 255, 255), pupil=(20, 20, 20)):
        for sd in (-1, 1):
            fill_ellipse(surf, col, c + sd * S * 0.13, y, S * 0.08, S * 0.09)
            fill_ellipse(surf, pupil, c + sd * S * 0.11, y + S * 0.02, S * 0.04, S * 0.045)
            thick_line(surf, (20, 20, 20), (c + sd * S * 0.24, y - S * 0.13), (c + sd * S * 0.04, y - S * 0.06), S * 0.04)

    if kind == "kernel":
        fill_poly(surf, (205, 198, 175), [(S * 0.1, S * 0.12), (S * 0.9, S * 0.12), (S * 0.9, S * 0.8), (S * 0.1, S * 0.8)])
        fill_poly(surf, (180, 20, 20), [(S * 0.17, S * 0.19), (S * 0.83, S * 0.19), (S * 0.83, S * 0.72), (S * 0.17, S * 0.72)])
        eyes(S * 0.4, (255, 220, 220))
        thick_line(surf, (255, 230, 230), (c - S * 0.15, S * 0.6), (c + S * 0.15, S * 0.6), S * 0.04)
        fill_poly(surf, (150, 145, 125), [(S * 0.35, S * 0.8), (S * 0.65, S * 0.8), (S * 0.75, S * 0.92), (S * 0.25, S * 0.92)])
    elif kind == "segfault":
        pts = []
        for i in range(16):
            a = i * math.tau / 16
            r = S * (0.42 if i % 2 == 0 else 0.33)
            pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
        fill_poly(surf, (120, 50, 170), pts)
        eyes(S * 0.45, (255, 255, 120))
        for k in range(5):
            x = S * (0.32 + k * 0.08)
            fill_poly(surf, (255, 255, 255), [(x, S * 0.62), (x + S * 0.06, S * 0.62), (x + S * 0.03, S * 0.7)])
        fill_poly(surf, (60, 255, 230), [(S * 0.15, S * 0.3), (S * 0.32, S * 0.3), (S * 0.32, S * 0.34), (S * 0.15, S * 0.34)])
    elif kind == "lockin":
        outer = ellipse_pts(c, S * 0.38, S * 0.22, S * 0.25, 0, 20, math.pi, math.tau)
        inner = ellipse_pts(c, S * 0.38, S * 0.13, S * 0.16, 0, 20, math.pi, math.tau)
        fill_poly(surf, (175, 180, 195), outer + [(c + S * 0.22, S * 0.45), (c + S * 0.13, S * 0.45)]
                  + inner[::-1] + [(c - S * 0.13, S * 0.45), (c - S * 0.22, S * 0.45)])
        fill_poly(surf, (230, 180, 40), [(S * 0.18, S * 0.4), (S * 0.82, S * 0.4), (S * 0.82, S * 0.92), (S * 0.18, S * 0.92)])
        eyes(S * 0.56)
        fill_ellipse(surf, (60, 40, 10), c, S * 0.76, S * 0.05, S * 0.05)
        fill_poly(surf, (60, 40, 10), [(c - S * 0.03, S * 0.77), (c + S * 0.03, S * 0.77), (c + S * 0.05, S * 0.87), (c - S * 0.05, S * 0.87)])
    else:
        fill_ellipse(surf, SKIN_TONE, c, c * 1.05, S * 0.32, S * 0.36)
        fill_poly(surf, (25, 25, 30), [(S * 0.16, S * 0.15), (S * 0.84, S * 0.15), (S * 0.84, S * 0.38), (S * 0.16, S * 0.38)])
        fill_ellipse(surf, (25, 25, 30), c, S * 0.15, S * 0.33, S * 0.12)
        fill_poly(surf, (25, 25, 30), [(S * 0.18, S * 0.42), (S * 0.82, S * 0.42), (S * 0.82, S * 0.56), (S * 0.18, S * 0.56)])
        for sd in (-1, 1):
            fill_ellipse(surf, (255, 255, 255), c + sd * S * 0.13, S * 0.49, S * 0.07, S * 0.05)
            fill_ellipse(surf, (20, 20, 20), c + sd * S * 0.12, S * 0.49, S * 0.03, S * 0.035)
        thick_line(surf, (120, 60, 50), (c - S * 0.1, S * 0.74), (c + S * 0.1, S * 0.72), S * 0.03)
    return pygame.transform.smoothscale(surf, (S // SS, S // SS))


# --------------------------------------------------------------------------- zombie process (front)
def zombie_front(px_per_m: float, phase: float = 0.0):
    cv = Canvas(px_per_m, 1.6, 1.7, foot_m=0.05)
    s = math.sin(phase * math.pi)
    body = (150, 175, 150)
    for side in (-1, 1):
        cv.line((90, 100, 95), (side * 0.12, 0.6), (side * 0.16 + s * side * 0.05, 0.05), 0.12)
    cv.poly(body, [(-0.28, 0.55), (0.28, 0.55), (0.3, 1.05), (-0.3, 1.05)])
    cv.rect((110, 130, 110), -0.28, 0.55, 0.28, 0.62)
    for side in (-1, 1):
        cv.line(body, (side * 0.27, 0.98), (side * 0.35, 0.95 + s * side * 0.06), 0.1)
        cv.line(body, (side * 0.35, 0.95 + s * side * 0.06), (side * 0.32, 0.8 + s * side * 0.06), 0.09)
    cv.ellipse((165, 190, 165), 0, 1.2, 0.22, 0.2)
    for side in (-1, 1):
        x = side * 0.09
        cv.line((40, 40, 40), (x - 0.04, 1.26), (x + 0.04, 1.18), 0.025)
        cv.line((40, 40, 40), (x - 0.04, 1.18), (x + 0.04, 1.26), 0.025)
    cv.line((60, 70, 60), (-0.07, 1.09), (0.07, 1.11), 0.025)
    # "Z" tag floating above the head
    zx, zy = 0.2, 1.45 + 0.04 * math.sin(phase * 2)
    cv.line((200, 255, 200), (zx - 0.06, zy + 0.06), (zx + 0.06, zy + 0.06), 0.025)
    cv.line((200, 255, 200), (zx + 0.06, zy + 0.06), (zx - 0.06, zy - 0.06), 0.025)
    cv.line((200, 255, 200), (zx - 0.06, zy - 0.06), (zx + 0.06, zy - 0.06), 0.025)
    return cv.result()


# --------------------------------------------------------------------------- pickups & power-ups
def pickup_surface(kind: str, width_px: int) -> pygame.Surface:
    if kind == "key":
        return key_surface(width_px)
    w = max(8, width_px) * SS
    h = int(w * 0.62)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    if kind == "golden":
        top, belly, fin = (230, 160, 20), (255, 225, 90), (200, 130, 10)
    else:
        top, belly, fin = (40, 120, 200), (170, 220, 250), (30, 90, 160)
    cx, cy = w * 0.44, h * 0.5
    fill_poly(surf, fin, [(w * 0.7, cy), (w * 0.98, h * 0.12), (w * 0.9, cy), (w * 0.98, h * 0.88)])
    fill_poly(surf, fin, [(w * 0.35, h * 0.25), (w * 0.55, h * 0.05), (w * 0.6, h * 0.3)])
    fill_ellipse(surf, top, cx, cy, w * 0.36, h * 0.33)
    fill_ellipse(surf, belly, cx, cy + h * 0.09, w * 0.32, h * 0.2)
    fill_ellipse(surf, (255, 255, 255), w * 0.2, cy - h * 0.06, w * 0.06, w * 0.06)
    fill_ellipse(surf, (15, 15, 20), w * 0.19, cy - h * 0.06, w * 0.03, w * 0.03)
    thick_line(surf, shade(top, 0.75), (w * 0.3, cy - h * 0.2), (w * 0.3, cy + h * 0.2), max(2, w * 0.02))
    return pygame.transform.smoothscale(surf, (w // SS, h // SS))


def key_surface(width_px: int) -> pygame.Surface:
    """An 'open-source key': a golden key whose bow is a green gear."""
    w = max(8, width_px) * SS
    h = int(w * 0.6)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cy = h / 2
    gx, r = w * 0.25, h * 0.38
    pts = []
    for i in range(16):
        a = i * math.tau / 16
        rr = r if i % 2 == 0 else r * 0.8
        pts.append((gx + math.cos(a) * rr, cy + math.sin(a) * rr))
    fill_poly(surf, (40, 170, 80), pts)
    fill_ellipse(surf, (255, 255, 255, 0), gx, cy, r * 0.35, r * 0.35)
    fill_ellipse(surf, (230, 245, 230), gx, cy, r * 0.35, r * 0.35)
    gold = (240, 190, 40)
    fill_poly(surf, gold, [(gx + r * 0.7, cy - h * 0.07), (w * 0.95, cy - h * 0.07), (w * 0.95, cy + h * 0.07),
                           (gx + r * 0.7, cy + h * 0.07)])
    for x in (w * 0.78, w * 0.9):
        fill_poly(surf, gold, [(x - w * 0.03, cy), (x + w * 0.03, cy), (x + w * 0.03, cy + h * 0.25),
                               (x - w * 0.03, cy + h * 0.25)])
    return pygame.transform.smoothscale(surf, (w // SS, h // SS))


POWERUP_GLOW = {
    "magnet": (255, 90, 90), "board": (90, 200, 255), "jetpack": (255, 160, 60),
    "superjump": (120, 255, 120), "coffee": (210, 150, 90),
}


def powerup_surface(kind: str, size_px: int) -> pygame.Surface:
    S = max(8, size_px) * SS
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2
    glow = POWERUP_GLOW[kind]
    for i in range(6, 0, -1):
        fill_ellipse(surf, (*glow, 25), c, c, S * 0.08 * i, S * 0.08 * i)
    fill_ellipse(surf, (255, 255, 255, 235), c, c, S * 0.36, S * 0.36)
    if kind == "magnet":
        pts_o = ellipse_pts(c, c * 0.95, S * 0.26, S * 0.26, 0, 24, 0, math.pi)
        pts_i = ellipse_pts(c, c * 0.95, S * 0.12, S * 0.12, 0, 24, 0, math.pi)
        outer = [(c + S * 0.26, c * 0.6), (c + S * 0.26, c * 0.95)] + pts_o + \
                [(c - S * 0.26, c * 0.95), (c - S * 0.26, c * 0.6),
                 (c - S * 0.12, c * 0.6), (c - S * 0.12, c * 0.95)] + pts_i[::-1] + \
                [(c + S * 0.12, c * 0.95), (c + S * 0.12, c * 0.6)]
        fill_poly(surf, (220, 40, 45), outer)
        for sx in (-1, 1):
            xa, xb = (c - S * 0.26, c - S * 0.12) if sx < 0 else (c + S * 0.12, c + S * 0.26)
            fill_poly(surf, (200, 205, 215), [(xa, c * 0.6), (xb, c * 0.6), (xb, c * 0.75), (xa, c * 0.75)])
    elif kind == "board":
        fill_ellipse(surf, (60, 130, 220), c, c, S * 0.3, S * 0.13, -0.4)
        fill_ellipse(surf, (200, 235, 255), c, c - S * 0.02, S * 0.26, S * 0.09, -0.4)
        thick_line(surf, (60, 130, 220), (c - S * 0.15, c + S * 0.1), (c + S * 0.12, c - S * 0.08), S * 0.03)
    elif kind == "jetpack":
        for sx in (-1, 1):
            x = c + sx * S * 0.1
            fill_poly(surf, (150, 155, 170), [(x - S * 0.08, c - S * 0.22), (x + S * 0.08, c - S * 0.22),
                                              (x + S * 0.08, c + S * 0.12), (x - S * 0.08, c + S * 0.12)])
            fill_ellipse(surf, (200, 30, 40), x, c - S * 0.22, S * 0.08, S * 0.05)
            fill_poly(surf, (255, 150, 30), [(x - S * 0.07, c + S * 0.12), (x + S * 0.07, c + S * 0.12), (x, c + S * 0.3)])
    elif kind == "superjump":
        for k in range(4):
            y = c + S * 0.2 - k * S * 0.09
            thick_line(surf, (60, 160, 60), (c - S * 0.15, y), (c + S * 0.15, y - S * 0.045), S * 0.035)
        fill_poly(surf, (40, 200, 70), [(c, c - S * 0.33), (c + S * 0.16, c - S * 0.14), (c - S * 0.16, c - S * 0.14)])
    elif kind == "coffee":
        cup = (245, 245, 245)
        fill_poly(surf, cup, [(c - S * 0.17, c - S * 0.08), (c + S * 0.17, c - S * 0.08),
                              (c + S * 0.13, c + S * 0.22), (c - S * 0.13, c + S * 0.22)])
        fill_ellipse(surf, (110, 65, 30), c, c - S * 0.08, S * 0.17, S * 0.05)
        pts = ellipse_pts(c + S * 0.18, c + S * 0.05, S * 0.08, S * 0.08, 0, 16, -math.pi / 2, math.pi / 2)
        for a, b in zip(pts, pts[1:]):
            thick_line(surf, cup, a, b, S * 0.03)
        for k in (-1, 1):
            x = c + k * S * 0.06
            thick_line(surf, (180, 180, 190), (x, c - S * 0.15), (x + S * 0.03, c - S * 0.3), S * 0.025)
    return pygame.transform.smoothscale(surf, (S // SS, S // SS))


def star_surface(size_px: int, filled: bool) -> pygame.Surface:
    S = max(8, size_px) * SS
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2
    pts = []
    for i in range(10):
        r = S * (0.48 if i % 2 == 0 else 0.2)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((c + math.cos(a) * r, c + math.sin(a) * r))
    fill_poly(surf, (90, 70, 20) if filled else (60, 60, 70), pts)
    inner = [(x * 0.82 + c * 0.18, y * 0.82 + c * 0.18) for x, y in pts]
    fill_poly(surf, (255, 205, 40) if filled else (120, 125, 140), inner)
    return pygame.transform.smoothscale(surf, (S // SS, S // SS))


def lock_surface(size_px: int) -> pygame.Surface:
    S = max(8, size_px) * SS
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    c = S / 2
    pts_o = ellipse_pts(c, S * 0.42, S * 0.22, S * 0.22, 0, 20, math.pi, math.tau)
    pts_i = ellipse_pts(c, S * 0.42, S * 0.13, S * 0.13, 0, 20, math.pi, math.tau)
    shackle = (pts_o + [(c + S * 0.22, S * 0.5), (c + S * 0.13, S * 0.5)] + pts_i[::-1]
               + [(c - S * 0.13, S * 0.5), (c - S * 0.22, S * 0.5)])
    fill_poly(surf, (170, 175, 190), shackle)
    fill_poly(surf, (240, 190, 50), [(S * 0.22, S * 0.45), (S * 0.78, S * 0.45), (S * 0.78, S * 0.9), (S * 0.22, S * 0.9)])
    fill_ellipse(surf, (90, 60, 10), c, S * 0.63, S * 0.05, S * 0.06)
    return pygame.transform.smoothscale(surf, (S // SS, S // SS))


def check_surface(size_px: int) -> pygame.Surface:
    S = max(8, size_px) * SS
    surf = pygame.Surface((S, S), pygame.SRCALPHA)
    fill_ellipse(surf, (60, 190, 90), S / 2, S / 2, S * 0.48, S * 0.48)
    thick_line(surf, (255, 255, 255), (S * 0.27, S * 0.52), (S * 0.43, S * 0.68), S * 0.09)
    thick_line(surf, (255, 255, 255), (S * 0.43, S * 0.68), (S * 0.74, S * 0.33), S * 0.09)
    return pygame.transform.smoothscale(surf, (S // SS, S // SS))


def app_icon(size_px: int = 256) -> pygame.Surface:
    surf = pygame.Surface((size_px, size_px), pygame.SRCALPHA)
    r = size_px // 2
    pygame.draw.circle(surf, (60, 140, 220), (r, r), r)
    pygame.draw.circle(surf, (200, 230, 250), (r, r), int(r * 0.9))
    tux = tux_front(int(size_px * 0.95), fish=True)
    surf.blit(tux, tux.get_rect(midbottom=(r + size_px * 0.04, size_px * 0.99)))
    return surf
