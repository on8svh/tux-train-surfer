"""Guards for a consistent release (version numbers, snap metadata, store assets)."""

import re
from pathlib import Path

from tux_train_surfer import __version__

ROOT = Path(__file__).resolve().parents[1]
SNAP = (ROOT / "snap" / "snapcraft.yaml").read_text(encoding="utf-8")


def snap_field(name: str) -> str:
    m = re.search(rf"^{name}:\s*'?([^'\n]+)'?\s*$", SNAP, re.M)
    assert m, name
    return m.group(1).strip()


def test_versions_match():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(rf'^version = "{re.escape(__version__)}"$', pyproject, re.M)
    assert snap_field("version") == __version__
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    first = re.search(r"^## (\S+)", changelog, re.M)
    assert first and first.group(1) == __version__


def test_snap_metadata():
    name = snap_field("name")
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,38}[a-z0-9]", name)
    assert len(snap_field("summary")) <= 78
    assert snap_field("base") == "core24"
    assert snap_field("confinement") == "strict"
    icon = ROOT / snap_field("icon")
    assert icon.is_file()
    desktop = ROOT / "snap" / "gui" / f"{name}.desktop"
    text = desktop.read_text(encoding="utf-8")
    assert f"Exec={name}" in text
    assert f"Icon=${{SNAP}}/meta/gui/{icon.name}" in text
    assert re.search(rf"^  {name}:$", SNAP, re.M), "app must be named like the snap"


def test_no_placeholders_left():
    for path in list(ROOT.glob("*.md")) + [ROOT / "pyproject.toml", ROOT / "snap" / "snapcraft.yaml"]:
        assert "YOUR-GITHUB-USER" not in path.read_text(encoding="utf-8"), path


def test_store_assets_present():
    store = ROOT / "docs" / "store"
    assert (store / "icon-512.png").is_file()
    assert (store / "banner-1920x640.png").is_file()
    assert len(list(store.glob("screenshot-*.png"))) == 5
