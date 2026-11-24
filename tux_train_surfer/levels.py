"""Level, theme and chaser definitions."""

from __future__ import annotations

import math
from dataclasses import dataclass

CHASERS = ("thief", "kernel", "segfault", "lockin")


@dataclass(frozen=True)
class Theme:
    key: str
    sky_top: tuple
    sky_bottom: tuple
    fog: tuple
    ground: tuple
    gravel: tuple = (120, 118, 125)
    sleeper: tuple = (92, 70, 58)
    rail: tuple = (190, 196, 210)
    scenery: tuple = ("pine", "pine", "house", "lamp")
    celestial: str = "sun"          # sun | moon | none
    celestial_color: tuple = (255, 245, 200)
    night: bool = False
    aurora: bool = False
    stars: bool = False
    snow: float = 0.0               # 0..1 snowfall intensity
    tunnel: str = ""                # "" | "rock" | "rack"
    rails: str = "steel"            # steel | data
    grid: bool = False              # glowing grid on the ground (terminal)
    mountains: tuple = (200, 215, 235)
    volcano: bool = False
    train_colors: tuple = ((214, 64, 52), (40, 110, 190), (240, 180, 40), (70, 160, 90))


THEMES = {t.key: t for t in (
    Theme("day", (90, 160, 235), (200, 228, 250), (210, 230, 248), (236, 242, 250),
          scenery=("pine", "pine", "house", "lamp", "igloo", "fence")),
    Theme("suburb", (120, 170, 220), (215, 230, 245), (220, 232, 245), (240, 244, 250),
          scenery=("house", "house", "pine", "snowman", "fence", "lamp"), snow=0.35),
    Theme("antarctica", (100, 165, 235), (225, 240, 252), (230, 242, 252), (245, 249, 255),
          scenery=("iceberg", "colony", "iceberg", "station", "colony", "flag"), mountains=(235, 245, 255)),
    Theme("harbour", (110, 165, 210), (205, 225, 240), (200, 220, 235), (220, 226, 232),
          gravel=(110, 110, 112), scenery=("crane", "container", "container", "lamp", "house"),
          mountains=(170, 190, 210)),
    Theme("iceland", (120, 140, 170), (200, 210, 220), (190, 200, 210), (60, 62, 66),
          gravel=(45, 45, 50), sleeper=(80, 62, 50), scenery=("geyser", "turfhouse", "volcano_rock", "geyser", "moss"),
          mountains=(90, 95, 105), volcano=True, celestial="none"),
    Theme("glacier", (70, 140, 220), (190, 225, 250), (205, 232, 250), (230, 245, 255),
          scenery=("iceberg", "pine", "iceberg", "igloo"), mountains=(225, 240, 255)),
    Theme("containers", (95, 150, 205), (200, 220, 238), (195, 215, 232), (190, 195, 200),
          gravel=(105, 105, 110), scenery=("stack", "stack", "crane", "container", "stack"),
          mountains=(150, 170, 190)),
    Theme("sunset", (70, 60, 140), (250, 160, 110), (240, 170, 140), (235, 215, 220),
          celestial_color=(255, 200, 120), scenery=("pine", "house", "lamp", "fence"),
          mountains=(150, 110, 150)),
    Theme("serverrack", (12, 16, 24), (30, 40, 55), (20, 28, 40), (45, 50, 60),
          gravel=(38, 42, 50), sleeper=(60, 60, 68), rail=(150, 160, 175), celestial="none",
          night=True, tunnel="rack", scenery=("rack",), mountains=(20, 25, 35),
          train_colors=((60, 70, 90), (90, 40, 40), (40, 80, 70), (80, 80, 90))),
    Theme("night", (10, 14, 40), (40, 50, 95), (35, 45, 85), (150, 165, 200),
          gravel=(70, 72, 85), sleeper=(60, 48, 42), rail=(150, 160, 185),
          celestial="moon", celestial_color=(240, 240, 255), night=True, stars=True,
          scenery=("house", "lamp", "pine", "lamp"), mountains=(30, 40, 75)),
    Theme("terminal", (0, 0, 0), (0, 25, 10), (0, 18, 6), (0, 10, 4),
          gravel=(0, 30, 12), sleeper=(0, 60, 25), rail=(60, 255, 120), celestial="none",
          night=True, rails="data", grid=True, scenery=("codecolumn", "termwindow", "codecolumn"),
          mountains=(0, 40, 15),
          train_colors=((20, 60, 30), (30, 30, 30), (10, 50, 60), (50, 50, 20))),
    Theme("blizzard", (150, 160, 175), (205, 210, 220), (215, 220, 228), (235, 238, 242),
          celestial="none", snow=1.0, scenery=("pine", "pine", "fence", "lamp"),
          mountains=(190, 195, 205)),
    Theme("tunnel", (30, 50, 80), (60, 110, 150), (45, 85, 120), (120, 170, 200),
          gravel=(80, 95, 110), sleeper=(70, 60, 60), celestial="none", night=True,
          tunnel="rock", scenery=("crystal", "crystal", "lamp"), mountains=(40, 70, 100)),
    Theme("aurora", (8, 20, 45), (20, 60, 90), (25, 55, 80), (160, 190, 215),
          gravel=(70, 80, 95), sleeper=(62, 50, 45), rail=(160, 175, 200),
          celestial="moon", night=True, aurora=True, stars=True, snow=0.2,
          scenery=("pine", "igloo", "pine", "lamp"), mountains=(25, 50, 75)),
    Theme("escape", (40, 15, 50), (160, 70, 90), (130, 70, 95), (210, 190, 210),
          gravel=(85, 75, 90), celestial="moon", celestial_color=(255, 220, 200),
          night=True, aurora=True, stars=True, snow=0.4,
          scenery=("house", "crane", "pine", "lamp", "container", "rack"), mountains=(70, 35, 70)),
)}

THEME_ORDER = tuple(THEMES)


@dataclass(frozen=True)
class Params:
    speed: float
    density: float
    moving: float
    ice: float
    ramp: float
    powerup: float
    zombies: float


@dataclass(frozen=True)
class Level:
    number: int                  # 0 = endless
    theme_key: str
    chaser: str
    length: float
    speed_start: float
    speed_end: float
    density: float
    moving: float
    ice: float
    zombies: float = 0.0
    ramp: float = 0.45
    powerup: float = 0.14
    fish_target: int = 150

    @property
    def endless(self) -> bool:
        return self.number == 0

    @property
    def name_key(self) -> str:
        return "endless" if self.endless else f"level_{self.number}"

    def theme_at(self, distance: float) -> Theme:
        if self.endless:
            idx = int(max(0.0, distance) // 1500) % len(THEME_ORDER)
            return THEMES[THEME_ORDER[idx]]
        return THEMES[self.theme_key]

    def params(self, distance: float) -> Params:
        if self.endless:
            d = max(0.0, distance)
            return Params(
                speed=min(31.0, 14.0 + d * 0.0042),
                density=min(0.95, 0.45 + d / 5000.0),
                moving=min(0.45, d / 7000.0),
                ice=min(0.35, 0.05 + d / 9000.0),
                ramp=0.45,
                powerup=0.15,
                zombies=min(0.4, d / 6000.0),
            )
        t = 0.0 if self.length <= 0 else max(0.0, min(1.0, distance / self.length))
        return Params(
            speed=self.speed_start + (self.speed_end - self.speed_start) * t,
            density=self.density, moving=self.moving, ice=self.ice,
            ramp=self.ramp, powerup=self.powerup, zombies=self.zombies,
        )

    def speed_at(self, distance: float) -> float:
        return self.params(distance).speed


LEVELS = (
    Level(1, "day", "thief", 650, 13.0, 15.0, 0.55, 0.00, 0.05, 0.00, ramp=0.7, fish_target=100),
    Level(2, "suburb", "thief", 800, 13.5, 16.0, 0.60, 0.00, 0.15, 0.00, ramp=0.6, fish_target=125),
    Level(3, "antarctica", "lockin", 900, 14.0, 16.5, 0.63, 0.05, 0.30, 0.00, ramp=0.6, fish_target=145),
    Level(4, "harbour", "thief", 1000, 14.5, 17.5, 0.66, 0.12, 0.10, 0.10, ramp=0.55, fish_target=165),
    Level(5, "iceland", "segfault", 1050, 15.0, 18.0, 0.68, 0.12, 0.25, 0.15, ramp=0.5, fish_target=180),
    Level(6, "glacier", "lockin", 1100, 15.5, 18.5, 0.70, 0.12, 0.35, 0.10, ramp=0.5, fish_target=190),
    Level(7, "containers", "lockin", 1200, 16.0, 19.5, 0.74, 0.20, 0.10, 0.20, ramp=0.5, fish_target=210),
    Level(8, "sunset", "segfault", 1250, 16.5, 20.0, 0.76, 0.22, 0.18, 0.20, ramp=0.45, fish_target=220),
    Level(9, "serverrack", "kernel", 1300, 17.0, 20.5, 0.78, 0.25, 0.05, 0.30, ramp=0.45, fish_target=230),
    Level(10, "night", "segfault", 1350, 17.0, 21.0, 0.80, 0.28, 0.15, 0.20, ramp=0.45, fish_target=240),
    Level(11, "terminal", "kernel", 1400, 17.5, 21.5, 0.82, 0.30, 0.10, 0.40, ramp=0.45, fish_target=250),
    Level(12, "blizzard", "thief", 1450, 18.0, 22.0, 0.84, 0.25, 0.40, 0.15, ramp=0.4, fish_target=260),
    Level(13, "tunnel", "segfault", 1500, 18.5, 23.0, 0.86, 0.32, 0.25, 0.25, ramp=0.4, fish_target=275),
    Level(14, "aurora", "lockin", 1650, 19.0, 24.0, 0.88, 0.36, 0.30, 0.25, ramp=0.4, fish_target=300),
    Level(15, "escape", "kernel", 1900, 19.5, 25.5, 0.92, 0.42, 0.32, 0.35, ramp=0.4, fish_target=340),
)

ENDLESS = Level(0, "day", "random", math.inf, 14.0, 31.0, 0.6, 0.2, 0.2, fish_target=0)


def level_by_number(number: int) -> Level:
    if number == 0:
        return ENDLESS
    for lvl in LEVELS:
        if lvl.number == number:
            return lvl
    raise KeyError(number)
