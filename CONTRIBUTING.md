# Contributing

Thanks for helping Tux escape!

- **Bugs and ideas**: open an issue. Include your OS, how you installed the game and the steps to reproduce.
- **Translations**: edit or add `tux_train_surfer/locale/<code>.json`. `pytest tests/test_data.py`
  checks that every key and placeholder is present.
- **Code**: run `ruff check .` and `pytest` before opening a pull request. Gameplay logic lives in
  `world.py` and has no pygame dependency, so add a test in `tests/test_world.py` for new mechanics.
- **Art and sound**: the game has no binary assets, so all art lives in `art.py` and `render.py`,
  and all sound in `audio.py`. Please keep it that way, so the whole game stays reproducible from
  source under the MIT licence.

By contributing you agree that your work is published under the MIT licence.
