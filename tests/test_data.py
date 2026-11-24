"""Translations, storage and missions."""

import json
import re

from tux_train_surfer import i18n
from tux_train_surfer.missions import MissionTracker, mission_set
from tux_train_surfer.storage import Save

PLACEHOLDER = re.compile(r"{[a-z]+}")


def test_all_locales_complete():
    en = json.loads((i18n.LOCALE_DIR / "en.json").read_text(encoding="utf-8"))
    langs = i18n.available()
    assert len(langs) >= 20
    for code in langs:
        data = json.loads((i18n.LOCALE_DIR / f"{code}.json").read_text(encoding="utf-8"))
        assert list(data) == list(en), code
        for k, v in en.items():
            assert sorted(PLACEHOLDER.findall(v)) == sorted(PLACEHOLDER.findall(data[k])), (code, k)


def test_language_detection(monkeypatch):
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "nl_BE.UTF-8")
    assert i18n.detect_language() == "nl"
    monkeypatch.setenv("LANGUAGE", "pt_BR:en")
    assert i18n.detect_language() == "pt"
    tr = i18n.Translator("auto")
    assert tr.code == "pt"
    tr.set_language("de")
    assert tr("level_n", n=3).endswith("3")


def test_save_roundtrip(tmp_path):
    s = Save(tmp_path / "save.json")
    s.bind_key("jump", "k")
    assert s.keys["jump"][0] == "k"
    s.bind_key("duck", "k")
    assert "k" not in s.keys["jump"] and s.keys["duck"][0] == "k"
    s.record_level(1, 1234, 50, [True, False, True])
    s2 = Save(tmp_path / "save.json")
    assert s2.progress["unlocked"] == 2
    assert s2.progress["best"]["1"] == 1234
    assert s2.keys["duck"][0] == "k"


def test_missions_raise_multiplier(tmp_path):
    s = Save(tmp_path / "save.json")
    m = MissionTracker(s)
    assert m.multiplier == 1
    first = mission_set(0)
    stats = {}
    for mission in first:
        stats[mission.stat] = mission.target
    assert len(m.check(stats)) == 3
    assert m.commit(stats) is True
    assert m.multiplier == 2


def test_total_missions_accumulate(tmp_path):
    s = Save(tmp_path / "save.json")
    m = MissionTracker(s)
    cables = next(x for x in m.current() if x.id == "cables")
    m.commit({"cables": cables.target - 1})
    assert not any(done for mm, v, done in m.progress() if mm.id == "cables")
    m.commit({"cables": 1})
    assert any(done for mm, v, done in m.progress() if mm.id == "cables")
