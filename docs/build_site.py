"""Builds docs/index.html (GitHub Pages) from one diff output folder.

    python src/main.py pulse --baseline yesterday --today 2026-03-18
    python docs/build_site.py
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

RUN = ROOT / "output" / "revenue_diff_yesterday_2026-03-17_vs_2026-03-18"


def main() -> None:
    head = dict(pd.read_csv(RUN / "summary_header.csv").values)
    summ = pd.read_csv(RUN / "summary.csv")
    tops = {c: pd.read_csv(RUN / f"top15_{c}.csv").head(5)[["account_id", "plan_tier", "annual_diff"]]
            .to_dict("records") for c in ["new", "upgrade", "downgrade", "churn"]}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        simulate_days.main()
    data = {
        "head": head,
        "summary": summ.to_dict("records"),
        "tops": tops,
        "guards": [l.strip() for l in buf.getvalue().splitlines() if l.startswith("  ")],
        "pulse": pulse.build_message(RUN),
    }
    html = (Path(__file__).parent / "template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(data, default=str))
    (Path(__file__).parent / "index.html").write_text(html, encoding="utf-8")
    print("docs/index.html written")


if __name__ == "__main__":
    main()
