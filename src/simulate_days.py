"""Replay a few days of the scheduler against a COPY of the snapshot store to
show every guard firing. The committed data/snapshots folder is not modified.

    python src/simulate_days.py
"""
import shutil
from datetime import date

import snapshot
from main import OUT, STORE, fetch_live

SIM = OUT / "simulation"


def main() -> None:
    if SIM.exists():
        shutil.rmtree(SIM)
    store, pending = SIM / "snapshots", SIM / "pending"
    shutil.copytree(STORE, store)

    def partial():                  # an extract that silently returned half the rows
        return fetch_live()[:50]

    steps = [
        ("03-18 08:55 scheduled run", fetch_live, date(2026, 3, 18), False),
        ("03-18 09:30 manual re-run", fetch_live, date(2026, 3, 18), False),
        ("03-19 08:55 partial extract", partial, date(2026, 3, 19), False),
        ("03-19 09:10 retry, file locked", fetch_live, date(2026, 3, 19), True),
        ("03-20 08:55 scheduled run", fetch_live, date(2026, 3, 20), False),
    ]
    print("Snapshot job")
    for label, fetch, day, locked in steps:
        print(f"  {label:32s} {snapshot.take_snapshot(fetch, store, day, pending, locked)}")

    print("\nBaseline lookup")
    for mode, day in [("yesterday", date(2026, 3, 20)), ("yesterday", date(2026, 3, 15)),
                      ("month-start", date(2026, 3, 20))]:
        path, real, note = snapshot.find_baseline(store, mode, day)
        print(f"  diff on {day} vs {mode:11s} -> {path.name}: {note}")


if __name__ == "__main__":
    main()
