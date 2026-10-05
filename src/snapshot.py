"""Daily snapshot job and baseline lookup, with guards.

Storage model: one file per day-of-month slot (`day_01.csv` ... `day_31.csv`),
re-used every month - the same shape as a workbook with one tab per day. Because
a slot name does not say which month it belongs to, every row carries the real
`snapshot_date`, and that marker is what the guards trust.

Guards
  1. once per day   - skip if today's slot already holds today's date
  2. completeness   - abort if the extract has fewer rows than expected
                      (a partial extract would turn missing accounts into fake churn)
  3. atomic write   - write to a temp file then rename; never a half-written slot
  4. pending queue  - if the slot cannot be written (e.g. file locked), park the
                      extract in pending/ and flush it on the next run
  5. baseline check - when diffing, the baseline slot's marker must match the
                      expected date; otherwise fall back to the latest valid
                      snapshot and report the real time span
"""
import csv
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

MIN_ROWS = 100          # tune to "normal row count minus a safety margin"


def slot(store: Path, d: date) -> Path:
    return store / f"day_{d.day:02d}.csv"


def marker(path: Path):
    """Real snapshot date stored in the slot, or None if the slot is empty/missing."""
    if not path.exists():
        return None
    with path.open(newline="") as f:
        first = next(csv.DictReader(f), None)
    return date.fromisoformat(first["snapshot_date"]) if first else None


def _write_atomic(rows: list, path: Path, locked: bool = False) -> None:
    if locked:                                  # used by the simulation
        raise PermissionError(f"{path.name} is open in another program")
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def flush_pending(store: Path, pending: Path) -> list:
    """Move parked snapshots into their slots (only if the slot is not newer)."""
    moved = []
    for p in sorted(pending.glob("*.csv")) if pending.exists() else []:
        d = date.fromisoformat(p.stem)
        current = marker(slot(store, d))
        if current is None or current <= d:
            shutil.move(str(p), slot(store, d))
            moved.append(d.isoformat())
    return moved


def take_snapshot(fetch, store: Path, today: date, pending: Path,
                  locked: bool = False) -> str:
    store.mkdir(parents=True, exist_ok=True)
    flushed = flush_pending(store, pending)
    prefix = f"flushed pending {flushed}; " if flushed else ""

    if marker(slot(store, today)) == today:
        return prefix + "SKIP: snapshot for today already taken"
    rows = fetch()
    if len(rows) < MIN_ROWS:
        return prefix + f"ABORT: only {len(rows)} rows (< {MIN_ROWS}), slot left untouched"
    for r in rows:
        r["snapshot_date"] = today.isoformat()
    try:
        _write_atomic(rows, slot(store, today), locked=locked)
        return prefix + f"OK: {len(rows)} rows -> {slot(store, today).name}"
    except PermissionError as e:
        pending.mkdir(parents=True, exist_ok=True)
        _write_atomic(rows, pending / f"{today.isoformat()}.csv")
        return prefix + f"PENDING: {e}; parked in pending/ for the next run"


def find_baseline(store: Path, mode: str, today: date):
    """Return (path, real_date, note) for the requested comparison baseline."""
    expected = today.replace(day=1) if mode == "month-start" else today - timedelta(days=1)
    path = slot(store, expected)
    if marker(path) == expected:
        return path, expected, f"baseline {expected} ({mode})"
    # fall back: newest slot whose marker is in [expected - 31 days, today)
    candidates = []
    for p in store.glob("day_*.csv"):
        d = marker(p)
        if d and expected - timedelta(days=31) <= d < today:
            candidates.append((d, p))
    if mode == "month-start":                   # never fall forward into the month
        candidates = [c for c in candidates if c[0] <= expected]
    if not candidates:
        raise RuntimeError(f"no valid baseline snapshot near {expected}")
    d, p = max(candidates)
    span = (today - d).days
    return p, d, (f"WARNING: slot for {expected} is missing or stale; using {d} "
                  f"instead - this diff covers {span} days, not a normal {mode} diff")
