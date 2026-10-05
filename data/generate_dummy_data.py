"""Generate synthetic recurring-revenue data for the change tracker.

Creates
  data/source_current.csv      the "live" revenue per account today (2026-03-18)
  data/snapshots/day_XX.csv    daily snapshot slots (one file per day of month)

Snapshot slots are re-used every month, so each row carries its real
`snapshot_date`. Slot day_18 is deliberately left over from LAST month to show
why the date marker - not the file name - must be trusted.

Some accounts are billed in a foreign currency; their reporting-currency value
moves with the exchange rate even when the price did not change.
Standard library only, fixed seed.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 7
N_ACCOUNTS = 120
TODAY = date(2026, 3, 18)
HERE = Path(__file__).parent
SNAP_DIR = HERE / "snapshots"
FIELDS = ["account_id", "plan_tier", "currency", "local_monthly", "fx_rate",
          "monthly_revenue", "snapshot_date"]
FX = {date(2026, 2, 18): 1.00, date(2026, 3, 1): 1.00, date(2026, 3, 15): 0.98,
      date(2026, 3, 16): 0.98, date(2026, 3, 17): 0.98, TODAY: 0.95}


def evolve(rng, book, p_new, p_churn, p_up, p_down, next_id):
    """Apply one period of business events to the account book (in place)."""
    for acc in list(book):
        r = rng.random()
        if r < p_churn:
            del book[acc]
        elif r < p_churn + p_up:
            book[acc]["local_monthly"] = round(book[acc]["local_monthly"] * rng.choice([1.3, 1.6, 2.0]))
        elif r < p_churn + p_up + p_down:
            book[acc]["local_monthly"] = round(book[acc]["local_monthly"] * rng.choice([0.5, 0.7]))
    for _ in range(int(p_new * len(book)) + 1):
        book[f"company_{next_id:03d}"] = new_account(rng)
        next_id += 1
    return next_id


def new_account(rng):
    tier = rng.choice(["starter", "growth", "growth", "scale", "enterprise"])
    base = {"starter": 50, "growth": 300, "scale": 1200, "enterprise": 5000}[tier]
    return {"plan_tier": tier,
            "currency": "FOREIGN" if rng.random() < 0.2 else "HOME",
            "local_monthly": round(base * rng.uniform(0.8, 1.5))}


def write(path, book, snap_date):
    rate = FX[snap_date]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for acc, a in sorted(book.items()):
            fx = rate if a["currency"] == "FOREIGN" else 1.0
            w.writerow({"account_id": acc, **a, "fx_rate": fx,
                        "monthly_revenue": round(a["local_monthly"] * fx, 2),
                        "snapshot_date": snap_date.isoformat()})
    print(f"wrote {len(book):3d} accounts -> {path.relative_to(HERE.parent)} ({snap_date})")


def main():
    rng = random.Random(SEED)
    SNAP_DIR.mkdir(exist_ok=True)
    book = {f"company_{i:03d}": new_account(rng) for i in range(1, N_ACCOUNTS + 1)}
    next_id = N_ACCOUNTS + 1

    # stale slot from last month (the slot "day_18" will be overwritten today)
    write(SNAP_DIR / "day_18.csv", book, date(2026, 2, 18))
    next_id = evolve(rng, book, 0.03, 0.02, 0.03, 0.02, next_id)
    write(SNAP_DIR / "day_01.csv", book, date(2026, 3, 1))     # start of month
    next_id = evolve(rng, book, 0.04, 0.03, 0.05, 0.03, next_id)
    write(SNAP_DIR / "day_15.csv", book, date(2026, 3, 15))
    write(SNAP_DIR / "day_16.csv", book, date(2026, 3, 16))
    next_id = evolve(rng, book, 0.01, 0.01, 0.02, 0.01, next_id)
    write(SNAP_DIR / "day_17.csv", book, date(2026, 3, 17))    # yesterday
    evolve(rng, book, 0.02, 0.02, 0.03, 0.02, next_id)
    write(HERE / "source_current.csv", book, TODAY)            # live system


if __name__ == "__main__":
    main()
