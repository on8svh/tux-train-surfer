"""Drives the real App with synthetic key presses (headless)."""

import pygame
import pytest

from tux_train_surfer import game
from tux_train_surfer.levels import level_by_number
from tux_train_surfer.main import parse_args


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAP_USER_DATA", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    args = parse_args(["--mute", "--resolution", "1280x720", "--lang", "en"])
    args.headless = True
    a = game.App(args)
    yield a
    pygame.quit()


def press(app, key, frames=1):
    ev = pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0)
    app.scene.handle(app.input.actions(ev), ev)
    for _ in range(frames):
        app.scene.update(1 / 60)


def test_keys_control_tux(app):
    app.go(game.PlayScene(app, level_by_number(1)))
    w = app.scene.world
    w.obstacles.clear()
    press(app, pygame.K_LEFT, 20)
    assert w.player.lane == -1
    press(app, pygame.K_d, 20)
    assert w.player.lane == 0
    press(app, pygame.K_SPACE, 5)
    assert not w.player.grounded
    press(app, pygame.K_ESCAPE)
    assert app.scene.paused
    press(app, pygame.K_ESCAPE)
    assert not app.scene.paused


def test_rebind_jump_key(app):
    app.go(game.ControlsScene(app))
    scene = app.scene
    press(app, pygame.K_DOWN)
    press(app, pygame.K_DOWN)          # third row = jump
    press(app, pygame.K_RETURN)
    assert scene.capture == "jump"
    press(app, pygame.K_j)
    assert scene.capture is None
    assert app.save.keys["jump"][0] == "j"
    app.go(game.PlayScene(app, level_by_number(1)))
    w = app.scene.world
    w.obstacles.clear()
    press(app, pygame.K_j, 3)
    assert not w.player.grounded


def test_menu_navigation_to_levels(app):
    app.go(game.TitleScene(app))
    press(app, pygame.K_RETURN)
    assert isinstance(app.scene, game.LevelSelectScene)
    press(app, pygame.K_RETURN)
    assert isinstance(app.scene, game.PlayScene)


def test_language_switch_in_settings(app):
    app.go(game.SettingsScene(app))
    for _ in range(4):
        press(app, pygame.K_DOWN)
    press(app, pygame.K_RIGHT)
    assert app.tr.code != "en" or app.save.settings["language"] != "auto"
