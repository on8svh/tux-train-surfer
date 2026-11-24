"""Runs the real game loop headless for every screen and a few levels."""

import os

import pytest

from tux_train_surfer.main import main


@pytest.fixture(autouse=True)
def isolated_save(tmp_path, monkeypatch):
    monkeypatch.setenv("SNAP_USER_DATA", str(tmp_path))
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")


@pytest.mark.parametrize("screen", ["title", "levels", "missions", "skins", "settings", "controls", "help"])
def test_menus(screen):
    assert main(["--smoke-test", "20", "--start", screen, "--resolution", "1280x720", "--mute"]) == 0


@pytest.mark.parametrize("level", [1, 5, 9, 11, 15, 0])
def test_play_levels(level, tmp_path):
    shot = tmp_path / f"level{level}.png"
    assert main(["--smoke-test", "240", "--level", str(level), "--autoplay", "--seed", "3",
                 "--resolution", "1280x720", "--mute", "--screenshot", str(shot)]) == 0
    assert shot.exists() and os.path.getsize(shot) > 10_000


@pytest.mark.parametrize("lang", ["nl", "ja", "ru"])
def test_languages(lang):
    assert main(["--smoke-test", "10", "--lang", lang, "--resolution", "1280x720", "--mute"]) == 0
