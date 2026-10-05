"""Generates the n8n workflow files in this folder.

I keep the workflows as code because the n8n editor makes it too easy to change one
node and forget the other. Credentials are only placeholders - after importing, open
the nodes with a red credential warning and pick your own.

    python automation/n8n/build_workflows.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
BI = {"httpHeaderAuth": {"id": "REPLACE_ME", "name": "BI API key"}}
SHEETS = {"googleApi": {"id": "REPLACE_ME", "name": "Sheets service account"}}
SLACK = {"slackApi": {"id": "REPLACE_ME", "name": "Slack bot"}}
SETTINGS = {"executionOrder": "v1", "timezone": "UTC",
            "errorWorkflow": "REPLACE_WITH_ERROR_HANDLER_ID"}
SHEET = "https://sheets.googleapis.com/v4/spreadsheets/{{$env.SNAPSHOT_SHEET_ID}}/values/"


def node(name, kind, x, params, version=1, creds=None):
    n = {"name": name, "type": f"n8n-nodes-base.{kind}", "typeVersion": version,
         "position": [x, 0], "parameters": params}
    if creds:
        n["credentials"] = creds
    return n


def chain(nodes):
    names = [n["name"] for n in nodes]
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]}
            for a, b in zip(names, names[1:])}


def schedule(name, hour, minute):
    return node(name, "scheduleTrigger", 0, {"rule": {"interval": [
        {"field": "cronExpression", "expression": f"{minute} {hour} * * *"}]}}, 1.2)


def http(name, x, method, url, creds, body=None, **extra):
    # neverError = keep the real error body from the API instead of n8n's generic one
    p = {"method": method, "url": url,
         "options": {"response": {"response": {"neverError": True}}}}
    if "httpHeaderAuth" in creds:
        p.update(authentication="genericCredentialType", genericAuthType="httpHeaderAuth")
    else:
        p.update(authentication="predefinedCredentialType",
                 nodeCredentialType=next(iter(creds)))
    if body is not None:
        p.update(sendBody=True, specifyBody="json", jsonBody=body)
    p.update(extra)
    return node(name, "httpRequest", x, p, 4.2, creds)


def code(name, x, js_file):
    return node(name, "code", x, {"jsCode": (HERE / "js" / js_file).read_text().strip()}, 2)


snapshot = [
    schedule("Every day 08:55", 8, 55),
    http("Fetch revenue per account", 220, "POST",
         "={{$env.BI_BASE_URL}}/api/card/{{$env.REVENUE_QUESTION_ID}}/query/json", BI),
    code("Guard: row count", 440, "guard_rows.js"),
    http("Clear today's slot", 660, "POST", "=" + SHEET + "{{$json.slot}}!A2:H:clear", SHEETS),
    http("Append rows (one request)", 880, "POST",
         "=" + SHEET + "{{$('Guard: row count').item.json.slot}}!A2:append?valueInputOption=RAW",
         SHEETS, body="={{ { values: $('Guard: row count').item.json.values } }}"),
]

diff = [
    schedule("Every day 09:05", 9, 5),
    http("Read today slot", 220, "GET",
         "=" + SHEET + "day_{{$now.toFormat('dd')}}!A2:H", SHEETS),
    http("Read yesterday slot", 440, "GET",
         "=" + SHEET + "day_{{$now.minus({days: 1}).toFormat('dd')}}!A2:H", SHEETS),
    code("Diff + top movers", 660, "diff.js"),
    http("Find today's KPI post", 880, "GET", "https://slack.com/api/conversations.history",
         SLACK, sendQuery=True, queryParameters={"parameters": [
             {"name": "channel", "value": "={{$env.PULSE_CHANNEL_ID}}"},
             {"name": "oldest", "value": "={{$today.toSeconds()}}"}]}),
    code("Pick thread", 1100, "pick_thread.js"),
    node("Post pulse", "slack", 1320, {
        "select": "channel",
        "channelId": {"__rl": True, "mode": "id", "value": "={{$env.PULSE_CHANNEL_ID}}"},
        "text": "={{$json.text}}",
        "otherOptions": {"thread_ts": {"replyValues": {"thread_ts": "={{$json.thread_ts}}"}}}},
        2.2, SLACK),
]

errors = [
    node("On workflow error", "errorTrigger", 0, {}),
    node("DM the owner", "slack", 220, {
        "select": "user",
        "user": {"__rl": True, "mode": "id", "value": "={{$env.ALERT_USER_ID}}"},
        "text": "=:rotating_light: *{{$json.workflow.name}}* failed\n"
                "{{$json.execution.error.message}}\n{{$json.execution.url}}"}, 2.2, SLACK),
]

for fname, title, nodes, settings in [
    ("01_daily_snapshot.json", "Revenue - daily snapshot", snapshot, SETTINGS),
    ("02_daily_diff_pulse.json", "Revenue - daily diff + Slack pulse", diff, SETTINGS),
    ("03_error_handler.json", "Error handler", errors, {"executionOrder": "v1"}),
]:
    wf = {"name": title, "nodes": nodes, "connections": chain(nodes), "settings": settings}
    (HERE / fname).write_text(json.dumps(wf, indent=2) + "\n")
    print(f"{fname}: {len(nodes)} nodes")
