"""Translations and automatic language detection.

Every language lives in ``locale/<code>.json``. To add a language, copy
``en.json``, translate the values and you are done - it is picked up
automatically.
"""

from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path

LOCALE_DIR = Path(__file__).with_name("locale")
FALLBACK = "en"

# Scripts that need a font with CJK glyphs.
CJK = {"zh", "ja", "ko"}

_ALIASES = {"no": "nb", "nn": "nb", "iw": "he", "in": "id", "zh-hans": "zh", "zh-hant": "zh"}


def available() -> dict[str, str]:
    """Map of language code -> native language name."""
    out = {}
    for path in sorted(LOCALE_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out[path.stem] = data.get("_name", path.stem)
    return out


def _normalise(tag: str | None) -> str | None:
    if not tag:
        return None
    tag = tag.split(".")[0].split("@")[0].replace("-", "_").lower()
    if tag in ("c", "posix"):
        return None
    base = tag.split("_")[0]
    return _ALIASES.get(tag.replace("_", "-"), _ALIASES.get(base, base))


def _windows_ui_language() -> str | None:
    try:
        import ctypes

        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
        return locale.windows_locale.get(lcid)
    except Exception:
        return None


def system_language_candidates() -> list[str]:
    cands: list[str] = []
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        if val:
            cands.extend(val.split(":"))
    if sys.platform == "win32":
        win = _windows_ui_language()
        if win:
            cands.append(win)
    try:
        loc = locale.getlocale()[0]
        if loc:
            cands.append(loc)
    except Exception:
        pass
    out = []
    for c in cands:
        n = _normalise(c)
        if n and n not in out:
            out.append(n)
    return out


def detect_language() -> str:
    langs = available()
    for cand in system_language_candidates():
        if cand in langs:
            return cand
    return FALLBACK


class Translator:
    def __init__(self, code: str = "auto") -> None:
        self.code = FALLBACK
        self._base = self._load(FALLBACK)
        self._strings: dict[str, str] = {}
        self.set_language(code)

    @staticmethod
    def _load(code: str) -> dict[str, str]:
        try:
            return json.loads((LOCALE_DIR / f"{code}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def set_language(self, code: str) -> None:
        if code == "auto" or code not in available():
            code = detect_language()
        self.code = code
        self._strings = self._load(code)

    def __call__(self, key: str, **kw) -> str:
        text = self._strings.get(key) or self._base.get(key) or key
        if kw:
            try:
                text = text.format(**kw)
            except (KeyError, IndexError, ValueError):
                pass
        return text

    @property
    def needs_cjk_font(self) -> bool:
        return self.code in CJK


# Font files known to contain CJK glyphs, tried in order. $SNAP is prefixed too.
CJK_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/wenquanyi/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/malgun.ttf",
)


def find_cjk_font() -> str | None:
    prefixes = [""]
    snap = os.environ.get("SNAP")
    if snap:
        prefixes.insert(0, snap)
    for cand in CJK_FONT_CANDIDATES:
        for pre in prefixes:
            path = pre + cand
            if os.path.isfile(path):
                return path
    return None
