"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__


def _resolution(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, e.g. 1920x1080") from exc


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="tux-train-surfer",
                                description="Tux Train Surfer - a free three-track runner starring Tux.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--fullscreen", action="store_true", help="start in fullscreen")
    p.add_argument("--windowed", action="store_true", help="start in a window")
    p.add_argument("--resolution", type=_resolution, help="render resolution, e.g. 1280x720 or 1920x1080")
    p.add_argument("--lang", help="language code (en, nl, fr, ...); default: system language")
    p.add_argument("--level", type=int, help="start directly in this level (0 = endless)")
    p.add_argument("--start", choices=("title", "levels", "play", "endless", "missions", "skins",
                                       "settings", "controls", "help"), help="first screen to show")
    p.add_argument("--seed", type=int, help="random seed for the track generator")
    p.add_argument("--mute", action="store_true", help="disable all sound")
    p.add_argument("--autoplay", action="store_true", help="let the autopilot play (demo mode)")
    p.add_argument("--unlock-all", action="store_true", help="unlock every level and skin (testing)")
    p.add_argument("--smoke-test", type=int, metavar="FRAMES", help="run N frames headless and exit")
    p.add_argument("--screenshot", metavar="PNG", help="with --smoke-test: save the last frame")
    p.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--quit-after", type=float, metavar="SECONDS", help=argparse.SUPPRESS)
    p.add_argument("--stats", action="store_true", help="print frame rate and audio status on exit")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.smoke_test:
        args.headless = True
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_VIDEO_X11_WMCLASS", "tux-train-surfer")
    os.environ.setdefault("SDL_APP_NAME", "Tux Train Surfer")
    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")

    import pygame

    try:
        pygame.mixer.pre_init(22050, -16, 1, 512, allowedchanges=0)
    except TypeError:
        pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()

    from .game import App

    try:
        app = App(args)
        return app.run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
