"""Revenue change tracker CLI.

    python src/main.py snapshot --today 2026-03-18
    python src/main.py diff --baseline month-start --today 2026-03-18
    python src/main.py diff --baseline yesterday   --today 2026-03-18
    python src/main.py pulse --baseline yesterday  --today 2026-03-18 [--send]

`--baseline` is required on purpose: "compared to what?" changes the answer
completely, so the tool refuses to guess.
"""
import argparse
import csv
from datetime import date
from pathlib import Path

import pandas as pd

import diff
import pulse
import snapshot

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "snapshots"
PENDING = ROOT / "data" / "pending"
SOURCE = ROOT / "data" / "source_current.csv"
OUT = ROOT / "output"


def fetch_live() -> list:
    """Stand-in for the live query (a SQL query / BI tool export in real life)."""
    with SOURCE.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.pop("snapshot_date", None)
    return rows


def run_diff(mode: str, today: date) -> Path:
    base_path, base_date, note = snapshot.find_baseline(STORE, mode, today)
    print(note)
    base = pd.read_csv(base_path)
    cur = pd.DataFrame(fetch_live())
    for c in ("local_monthly", "fx_rate", "monthly_revenue"):
        cur[c] = cur[c].astype(float)
    if cur.empty:
        raise SystemExit("STOP: current extract is empty - every account would look churned")

    detail = diff.compare(base, cur)
    summ = diff.summary(detail, base["monthly_revenue"].sum(), cur["monthly_revenue"].sum())
    tops = diff.top_movers(detail)
    header = pd.DataFrame([
        {"item": "baseline", "value": f"{base_date} ({mode})"},
        {"item": "current", "value": str(today)},
        {"item": "baseline ARR", "value": round(base["monthly_revenue"].sum() * 12, 2)},
        {"item": "current ARR", "value": round(cur["monthly_revenue"].sum() * 12, 2)},
        {"item": "bridge check", "value": "OK" if summ.attrs["bridge_ok"] else "FAILED"},
        {"item": "note", "value": note},
    ])

    stem = f"revenue_diff_{mode}_{base_date}_vs_{today}"
    out_dir = OUT / stem
    out_dir.mkdir(parents=True, exist_ok=True)
    header.to_csv(out_dir / "summary_header.csv", index=False)
    summ.to_csv(out_dir / "summary.csv", index=False)
    detail.to_csv(out_dir / "detail.csv", index=False)
    for cat, df in tops.items():
        df.to_csv(out_dir / f"top15_{cat}.csv", index=False)
    try:                                    # one workbook with a sheet per table
        with pd.ExcelWriter(OUT / f"{stem}.xlsx") as xw:
            header.to_excel(xw, sheet_name="Summary", index=False)
            summ.to_excel(xw, sheet_name="Summary", index=False, startrow=len(header) + 2)
            for cat, df in tops.items():
                df.to_excel(xw, sheet_name=f"Top 15 {cat}", index=False)
            detail.to_excel(xw, sheet_name="Detail", index=False)
    except ImportError:
        print("openpyxl not installed - CSV output only")

    print(header.to_string(index=False))
    print()
    print(summ.to_string(index=False))
    for cat, df in tops.items():
        print(f"\nTop {min(len(df), 5)} {cat} (of {len(df)} shown in output):")
        print(df.head(5)[["account_id", "plan_tier", "annual_base", "annual_now",
                          "annual_diff", "fx_effect"]].to_string(index=False))
    print(f"\noutput -> {out_dir}")
    return out_dir


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--today", type=date.fromisoformat, default=date.today())
    d = sub.add_parser("diff")
    d.add_argument("--baseline", choices=["month-start", "yesterday"], required=True)
    d.add_argument("--today", type=date.fromisoformat, default=date.today())
    u = sub.add_parser("pulse", help="diff + Slack message (dry-run unless --send)")
    u.add_argument("--baseline", choices=["month-start", "yesterday"], required=True)
    u.add_argument("--today", type=date.fromisoformat, default=date.today())
    u.add_argument("--send", action="store_true")
    a = p.parse_args()
    if a.cmd == "snapshot":
        status = snapshot.take_snapshot(fetch_live, STORE, a.today, PENDING)
        print(status)
        # non-zero exit lets the scheduler's error handler send an alert
        raise SystemExit(1 if status.split(":")[0].endswith(("ABORT", "PENDING")) else 0)
    elif a.cmd == "diff":
        run_diff(a.baseline, a.today)
    else:
        print(pulse.run(run_diff(a.baseline, a.today), a.today, a.send))


if __name__ == "__main__":
    main()
