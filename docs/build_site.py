"""Builds docs/index.html (GitHub Pages) from the diff output folders.

    python src/main.py diff  --baseline month-start --today 2026-03-18
    python src/main.py pulse --baseline yesterday   --today 2026-03-18
    python docs/build_site.py

Both baselines are baked into one static page, no server needed.
"""
import contextlib
import io
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import pulse          # noqa: E402
import simulate_days  # noqa: E402

RUNS = {
    "yesterday": ROOT / "output" / "revenue_diff_yesterday_2026-03-17_vs_2026-03-18",
    "month-start": ROOT / "output" / "revenue_diff_month-start_2026-03-01_vs_2026-03-18",
}
CATS = ["new", "upgrade", "downgrade", "churn"]


def run_data(folder: Path) -> dict:
    return {
        "head": dict(pd.read_csv(folder / "summary_header.csv").values),
        "summary": pd.read_csv(folder / "summary.csv").to_dict("records"),
        "tops": {c: pd.read_csv(folder / f"top15_{c}.csv")[["account_id", "plan_tier", "currency", "annual_diff"]]
                 .to_dict("records") for c in CATS},
        "pulse": pulse.build_message(folder),
    }


def profile(path: Path, purpose: str) -> dict:
    """Shape of one synthetic input file, shown on the page so readers know what the numbers stand on."""
    df = pd.read_csv(path)
    cols = []
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s):
            desc = f"number · {s.min():,.2f} to {s.max():,.2f}"
        else:
            u = s.dropna().unique()
            desc = f"text · {len(u)} values" + (f" ({', '.join(map(str, sorted(u)[:4]))})" if len(u) <= 4 else f", e.g. {u[0]}")
        cols.append({"name": c, "desc": desc, "nulls": int(s.isna().sum())})
    return {"file": str(path.relative_to(ROOT)).replace("\\", "/"), "purpose": purpose, "rows": len(df),
            "ids": int(df["account_id"].nunique()), "id_col": "account_id",
            "period": ", ".join(sorted(map(str, df["snapshot_date"].unique()))), "columns": cols}


def main() -> None:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        simulate_days.main()
    snaps = sorted((ROOT / "data" / "snapshots").glob("*.csv"))
    data = {
        "runs": {k: run_data(v) for k, v in RUNS.items()},
        "guards": [line.strip() for line in buf.getvalue().splitlines() if line.startswith("  ")],
        "profile": {
            "generator": "data/generate_dummy_data.py", "seed": 7,
            "files": [profile(ROOT / "data" / "source_current.csv", "today's revenue per account (what the BI query would return)")]
                     + [profile(p, "stored snapshot slot") for p in snaps[:1]],
            "snapshots": [str(p.relative_to(ROOT)).replace("\\", "/") for p in snaps],
            "quirks": ["accounts billed in a foreign currency (exchange-rate moves)", "new, upgraded, downgraded and churned accounts",
                       "a stale snapshot slot to trigger the guards"],
        },
    }
    html = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(data, default=str))
    (Path(__file__).parent / "index.html").write_text(html, encoding="utf-8")
    print("docs/index.html written")


if __name__ == "__main__":
    main()
