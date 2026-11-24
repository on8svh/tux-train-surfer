"""Missions: three at a time. Finishing a set raises the permanent score multiplier."""

from __future__ import annotations

from dataclasses import dataclass

# mission id -> (stat name in World.stats, scope)
MISSION_TYPES = {
    "fish_run": ("fish", "run"),
    "distance_run": ("distance", "run"),
    "score_run": ("score", "run"),
    "cables": ("cables", "total"),
    "rolls": ("rolls", "total"),
    "firewalls": ("firewalls", "total"),
    "zombies": ("zombies", "total"),
    "keys": ("keys", "total"),
    "magnet": ("magnet", "total"),
    "jetpack": ("jetpack", "total"),
    "board": ("board", "total"),
    "superjumps": ("superjumps", "total"),
    "coffee": ("coffee", "total"),
    "roof_m": ("roof_m", "total"),
    "slips": ("slips", "total"),
}

BASE_SETS = (
    (("fish_run", 50), ("cables", 5), ("firewalls", 5)),
    (("rolls", 10), ("distance_run", 800), ("magnet", 2)),
    (("fish_run", 100), ("zombies", 5), ("jetpack", 1)),
    (("keys", 3), ("board", 2), ("superjumps", 5)),
    (("roof_m", 300), ("coffee", 3), ("fish_run", 150)),
    (("rolls", 25), ("distance_run", 1500), ("firewalls", 30)),
    (("score_run", 20000), ("jetpack", 3), ("zombies", 20)),
    (("keys", 10), ("fish_run", 250), ("slips", 10)),
)

MAX_MULTIPLIER = 30


@dataclass(frozen=True)
class Mission:
    id: str
    target: int

    @property
    def stat(self) -> str:
        return MISSION_TYPES[self.id][0]

    @property
    def scope(self) -> str:
        return MISSION_TYPES[self.id][1]

    @property
    def text_key(self) -> str:
        return "m_" + self.id


def mission_set(index: int) -> list[Mission]:
    base = BASE_SETS[index % len(BASE_SETS)]
    factor = 1 + index // len(BASE_SETS)
    return [Mission(mid, target * factor) for mid, target in base]


class MissionTracker:
    """Works on the ``missions`` section of the save data."""

    def __init__(self, save) -> None:
        self.save = save

    @property
    def data(self) -> dict:
        return self.save.data["missions"]

    @property
    def multiplier(self) -> int:
        return min(MAX_MULTIPLIER, 1 + self.data["set"])

    def current(self) -> list[Mission]:
        return mission_set(self.data["set"])

    def _value(self, m: Mission, run_stats) -> int:
        run = int(run_stats.get(m.stat, 0)) if run_stats else 0
        if m.scope == "run":
            return run
        return int(self.data["progress"].get(m.id, 0)) + run

    def progress(self, run_stats=None) -> list[tuple[Mission, int, bool]]:
        done = set(self.data["done"])
        out = []
        for m in self.current():
            if m.id in done:
                out.append((m, m.target, True))
            else:
                v = self._value(m, run_stats)
                out.append((m, min(v, m.target), v >= m.target))
        return out

    def check(self, run_stats) -> list[Mission]:
        """Missions that became complete during the current run (marked done immediately)."""
        newly = []
        done = self.data["done"]
        for m in self.current():
            if m.id not in done and self._value(m, run_stats) >= m.target:
                done.append(m.id)
                newly.append(m)
        return newly

    def commit(self, run_stats) -> bool:
        """End of a run: add totals, advance the set if all three are done. Returns True on level-up."""
        self.check(run_stats)
        prog = self.data["progress"]
        for m in self.current():
            if m.scope == "total" and m.id not in self.data["done"]:
                prog[m.id] = int(prog.get(m.id, 0)) + int(run_stats.get(m.stat, 0))
        levelled = False
        if len(set(self.data["done"]) & {m.id for m in self.current()}) == 3:
            self.data["set"] += 1
            self.data["progress"] = {}
            self.data["done"] = []
            levelled = True
        self.save.save()
        return levelled
