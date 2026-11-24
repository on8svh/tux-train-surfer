# Publishing Tux Train Surfer

Repository: https://github.com/on8svh/tux-train-surfer
Snap name: `tux-train-surfer` (not published by anyone as of 2026-11-24; registration still has to be done)

The snap can't be built on Windows. GitHub Actions builds it for amd64 and arm64, installs it on
the runner, starts the game headless as a smoke test, and uploads it to the Snap Store.

## 1. Push to GitHub (once)

1. Create an **empty** public repository `tux-train-surfer` under the `on8svh` account
   (no README or licence, because the project already has them).
2. In this folder:
   ```bash
   git remote add origin https://github.com/on8svh/tux-train-surfer.git
   git push -u origin main
   ```
3. On GitHub, under **Actions**, check that **CI** (tests on Linux and Windows) and **Snap** both
   go green. Download the `snap-ubuntu-latest` artifact if you want to try the snap yourself.

## 2. Snap Store account and name (once)

On a Linux machine (or any Ubuntu VM), with `sudo snap install snapcraft --classic`:

```bash
snapcraft login                      # Ubuntu One account
snapcraft register tux-train-surfer
```

If the name turns out to be taken, change `name:` in `snap/snapcraft.yaml`, rename
`snap/gui/tux-train-surfer.desktop` and `.svg` to match, and update `Exec=`/`Icon=` in the
desktop file. `pytest tests/test_release.py` checks that everything matches.

## 3. Let GitHub publish (once)

```bash
snapcraft export-login --snaps=tux-train-surfer \
  --acls package_access,package_push,package_update,package_release credentials.txt
```

Add the contents of `credentials.txt` as the repository secret **`SNAPCRAFT_STORE_CREDENTIALS`**
(Settings → Secrets and variables → Actions → New repository secret), then delete the file.

From then on, every push to `main` publishes to the **edge** channel.

## 4. Store listing (once)

On https://snapcraft.io/tux-train-surfer/listing:

| Field | Value |
|-------|-------|
| Category | Games (primary) |
| Icon | `docs/store/icon-512.png` (the SVG in `snap/gui` is used inside the snap) |
| Banner | `docs/store/banner-1920x640.png` |
| Screenshots | the five `docs/store/screenshot-*.png` |
| Contact, source, website | already set from `snap/snapcraft.yaml` |
| License | MIT (from `snapcraft.yaml`) |

Regenerate the images at any time with `python tools/make_store_assets.py`. They're drawn by the
game's own code, so they fall under the same licence.

Optional: ask on https://forum.snapcraft.io (category *store-requests*) for **auto-connection of
the `joystick` interface**. Until that's granted, gamepad users run
`sudo snap connect tux-train-surfer:joystick` once. This is also in the store description.

## 5. Release a version

1. Bump the version in `tux_train_surfer/__init__.py`, `pyproject.toml` and
   `snap/snapcraft.yaml`, and add a section at the top of `CHANGELOG.md`.
   `pytest tests/test_release.py` fails if one of them is forgotten.
2. Commit, then tag and push:
   ```bash
   git tag v1.0.0
   git push origin main v1.0.0
   ```
3. The Snap workflow uploads to the **stable** channel and creates a GitHub Release with the
   `.snap` files attached.
4. Test it with `sudo snap install tux-train-surfer` (or `--edge` for the latest main build).

## What the first store review looks at

- Strict confinement with only standard desktop interfaces (`audio-playback`, `joystick`,
  `opengl`, `wayland`, `x11` plus the GNOME extension), so no manual review is needed.
- Saves and the music cache are stored in `$SNAP_USER_DATA`.
- Bundled third-party packages: Python 3.12 (from Ubuntu), pygame/SDL2 (LGPL, from PyPI) and
  fonts-droid-fallback (Apache-2.0, for Chinese, Japanese and Korean). Everything else is in this
  repository under MIT.
