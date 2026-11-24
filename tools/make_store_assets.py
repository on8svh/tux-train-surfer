"""Generate the Snap Store / GitHub listing images from the game's own code.

    python tools/make_store_assets.py

Writes into docs/store/:
  icon-512.png        store icon (the SVG in snap/gui is used inside the snap)
  banner-1920x640.png store banner (3:1)
  screenshot-*.png    five 1920x1080 in-game screenshots
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "store"

SHOTS = (
    ("01-ice-station", ["--level", "1", "--seed", "4", "--smoke-test", "300"]),
    ("02-terminal-railway", ["--level", "11", "--seed", "4", "--smoke-test", "360"]),
    ("03-server-rack-tunnel", ["--level", "9", "--seed", "8", "--smoke-test", "420"]),
    ("04-iceland-geysers", ["--level", "5", "--seed", "6", "--smoke-test", "300"]),
    ("05-skins", ["--start", "skins", "--unlock-all", "--smoke-test", "30"]),
)


def screenshots() -> None:
    from tux_train_surfer.main import main

    for name, args in SHOTS:
        main(args + ["--autoplay", "--mute", "--lang", "en", "--resolution", "1920x1080",
                     "--screenshot", str(OUT / f"screenshot-{name}.png")])


def icon_and_banner() -> None:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame

    pygame.init()
    pygame.display.set_mode((1, 1))
    from tux_train_surfer import art
    from tux_train_surfer.i18n import Translator
    from tux_train_surfer.levels import level_by_number
    from tux_train_surfer.render import Renderer
    from tux_train_surfer.ui import UI, WHITE, YELLOW
    from tux_train_surfer.world import Bot, World

    pygame.image.save(art.app_icon(512), str(OUT / "icon-512.png"))

    W, H = 1920, 640
    banner = pygame.Surface((W, H))
    world = World(level_by_number(14), seed=11)
    bot = Bot(world)
    r = Renderer(W, H)
    r.horizon = H * 0.42
    for _ in range(240):
        bot.update(1 / 60)
        world.update(1 / 60)
        r.follow(world, 1 / 60)
    r.draw(banner, world, 4.0, 1 / 60)
    ui = UI(W, 1080, Translator("en"))
    ui.panel(banner, pygame.Rect(int(W * 0.37), int(H * 0.14), int(W * 0.5), int(H * 0.64)), (8, 16, 40, 170))
    ui.text(banner, "Tux Train Surfer", 150, (W * 0.62, H * 0.33), YELLOW)
    ui.text(banner, "Outrun the bugs, surf the trains, grab the fish!", 48, (W * 0.62, H * 0.55), WHITE)
    ui.text(banner, "Free & open source - 15 worlds - 26 languages", 36, (W * 0.62, H * 0.68), (190, 230, 255))
    tux = art.tux_front(560)
    banner.blit(tux, tux.get_rect(midbottom=(W * 0.17, H + 20)))
    for i, kind in enumerate(("thief", "kernel", "segfault", "lockin")):
        img = art.chaser_front(kind, 120)
        banner.blit(img, img.get_rect(center=(W * 0.5 + i * 150, H * 0.86)))
    pygame.image.save(banner, str(OUT / "banner-1920x640.png"))
    pygame.quit()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ["SNAP_USER_DATA"] = tempfile.mkdtemp(prefix="tts-assets-")  # don't touch real saves
    icon_and_banner()
    screenshots()
    for p in sorted(OUT.iterdir()):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size // 1024} KB")
