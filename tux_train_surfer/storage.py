"""Settings, key bindings and progress, stored as JSON in the user data folder."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

from . import config as C

ACTIONS = ("left", "right", "jump", "duck", "pause")

# Keys are stored as pygame key *names* (pygame.key.name) so the file is readable.
DEFAULT_KEYS = {
    "left": ["left", "a"],
    "right": ["right", "d"],
    "jump": ["up", "w", "space"],
    "duck": ["down", "s"],
    "pause": ["escape", "p"],
}
# Gamepad buttons (SDL game controller layout: 0=A 1=B 2=X 3=Y 7=Start on most pads)
DEFAULT_PAD = {
    "left": [],
    "right": [],
    "jump": [0],
    "duck": [1],
    "pause": [7],
}

DEFAULTS = {
    "version": 1,
    "settings": {
        "fullscreen": False,
        "resolution": None,       # [w, h] or None = automatic
        "music": 0.6,
        "sfx": 0.8,
        "language": "auto",
        "skin": "classic",
    },
    "missions": {
        "set": 0,
        "progress": {},
        "done": [],
    },
    "keys": DEFAULT_KEYS,
    "pad": DEFAULT_PAD,
    "progress": {
        "unlocked": 1,
        "stars": {},              # "level" -> [finish, fish, clean]
        "best": {},               # "level" -> score
        "best_fish": {},
        "endless_best": 0,
        "total_fish": 0,
        "total_keys": 0,
    },
}


def data_dir() -> Path:
    snap = os.environ.get("SNAP_USER_DATA")
    if snap:
        return Path(snap)
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "TuxTrainSurfer"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TuxTrainSurfer"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / C.APP_ID


def _merge(defaults, loaded):
    if isinstance(defaults, dict) and isinstance(loaded, dict):
        out = {}
        for k, v in defaults.items():
            out[k] = _merge(v, loaded[k]) if k in loaded else copy.deepcopy(v)
        for k, v in loaded.items():
            if k not in out:
                out[k] = v
        return out
    if defaults is None or loaded is None or type(defaults) is type(loaded):
        return loaded
    if isinstance(defaults, float) and isinstance(loaded, int):
        return float(loaded)
    return copy.deepcopy(defaults)


class Save:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (data_dir() / "save.json")
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    # ---------------------------------------------------------------- io
    def load(self) -> None:
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.data = _merge(DEFAULTS, loaded)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ---------------------------------------------------------------- shortcuts
    @property
    def settings(self) -> dict:
        return self.data["settings"]

    @property
    def progress(self) -> dict:
        return self.data["progress"]

    @property
    def keys(self) -> dict:
        return self.data["keys"]

    @property
    def pad(self) -> dict:
        return self.data["pad"]

    def reset_controls(self) -> None:
        self.data["keys"] = copy.deepcopy(DEFAULT_KEYS)
        self.data["pad"] = copy.deepcopy(DEFAULT_PAD)

    def bind_key(self, action: str, key_name: str) -> None:
        """Make key_name the primary key of action and remove it from other actions."""
        for a in ACTIONS:
            self.keys[a] = [k for k in self.keys.get(a, []) if k != key_name]
        lst = self.keys.setdefault(action, [])
        lst.insert(0, key_name)
        del lst[3:]

    def bind_pad(self, action: str, button: int) -> None:
        for a in ACTIONS:
            self.pad[a] = [b for b in self.pad.get(a, []) if b != button]
        self.pad[action] = [button]

    # ---------------------------------------------------------------- progress
    def record_level(self, number: int, score: int, fish: int, stars: list[bool], keys: int = 0) -> bool:
        p = self.progress
        p["total_keys"] += keys
        key = str(number)
        old = p["stars"].get(key, [False, False, False])
        p["stars"][key] = [a or b for a, b in zip(old, stars)]
        p["best_fish"][key] = max(p["best_fish"].get(key, 0), fish)
        p["total_fish"] += fish
        record = score > p["best"].get(key, 0)
        if record:
            p["best"][key] = score
        if stars[0]:
            p["unlocked"] = max(p["unlocked"], number + 1)
        self.save()
        return record

    def record_endless(self, score: int, fish: int, keys: int = 0) -> bool:
        p = self.progress
        p["total_fish"] += fish
        p["total_keys"] += keys
        record = score > p["endless_best"]
        if record:
            p["endless_best"] = score
        self.save()
        return record
