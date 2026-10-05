"""Daily revenue pulse: turn a diff output folder into a Slack message.

    python src/main.py pulse --baseline yesterday --today 2026-03-18          # dry-run
    python src/main.py pulse --baseline yesterday --today 2026-03-18 --send   # post

The message answers "the number moved - because of whom?": net ARR change, counts per
category and the top movers. It replies in the thread of the day's KPI post when one is
found (see THREAD_MATCH), otherwise it posts to the channel.
"""
from datetime import datetime, time
from pathlib import Path

import pandas as pd

import slack_client

TOP_IN_MESSAGE = 5
THREAD_MATCH = "Daily revenue"          # text of the KPI post the pulse replies under
ORDER = ["new", "upgrade", "downgrade", "churn"]
ICON = {"new": ":large_green_circle:", "upgrade": ":arrow_up:",
        "downgrade": ":arrow_down:", "churn": ":red_circle:"}


def money(v: float) -> str:
    sign = "-" if v < 0 else "+"
    return f"{sign}{abs(v):,.0f}"


def build_message(out_dir: Path) -> dict:
    head = dict(pd.read_csv(out_dir / "summary_header.csv").values)
    summ = pd.read_csv(out_dir / "summary.csv").set_index("category")
    net = summ.loc["TOTAL", "annual_diff"]

    lines = []
    for cat in ORDER:
        if cat not in summ.index or summ.loc[cat, "accounts"] == 0:
            continue
        top = pd.read_csv(out_dir / f"top15_{cat}.csv").head(TOP_IN_MESSAGE)
        movers = ", ".join(f"`{r.account_id}` {money(r.annual_diff)}" for r in top.itertuples())
        lines.append(f"{ICON[cat]} *{cat}* - {int(summ.loc[cat, 'accounts'])} accounts, "
                     f"{money(summ.loc[cat, 'annual_diff'])}\n      {movers}")
    if "fx_only" in summ.index and summ.loc["fx_only", "accounts"] > 0:
        lines.append(f":currency_exchange: *fx only* - {int(summ.loc['fx_only', 'accounts'])} "
                     f"accounts, {money(summ.loc['fx_only', 'annual_diff'])} (exchange rate, no plan change)")

    note = str(head.get("note", ""))
    warn = f"\n:warning: {note}" if note.startswith("WARNING") else ""
    bridge = head.get("bridge check")
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text":
            f"*Revenue movers* - {head['current']} vs {head['baseline']}\n"
            f"ARR {float(head['current ARR']):,.0f} (net {money(net)}){warn}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines) or "_no changes_"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text":
            f"Bridge check: {bridge} | annual value = monthly x 12 | top {TOP_IN_MESSAGE} "
            f"per category, full list in the report"}]},
    ]
    text = f"Revenue movers {head['current']}: net {money(net)}"
    return {"text": text, "blocks": blocks}


def run(out_dir: Path, today, send: bool) -> str:
    message = build_message(out_dir)
    thread_ts = None
    if send:
        try:
            midnight = datetime.combine(today, time.min).timestamp()
            thread_ts = slack_client.find_thread(THREAD_MATCH, midnight)
        except KeyError:
            pass                                   # webhook mode: no history lookup
    return slack_client.post(message, send=send, thread_ts=thread_ts,
                             preview=out_dir / "pulse_preview.json")
