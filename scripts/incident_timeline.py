"""Build the investigation timeline for incident INC-77031 (synthetic data).

Merges role changes, authentication events and billing adjustments for the subject
account into one ordered timeline, and tags each event with the detection condition
it satisfies. Output: output/incident_timeline.csv

Run from the repository root:
    python scripts/incident_timeline.py
"""
import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "output"
OUT.mkdir(exist_ok=True)


def load(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


changes = load("role_change_log.csv")
subject = changes[0]["user_id"]
known_hosts = {a["host"] for a in load("asset_inventory.csv")}
grant_ts = datetime.fromisoformat(changes[0]["ts"])

events = []
for c in changes:
    tags = []
    if c["action"] == "GRANT" and not c["expiry"]:
        tags.append("Emergency grant, no expiry")
    events.append((c["ts"], "Role change", f"{c['action']} {c['role_code']} by {c['changed_by']} ({c['ticket']}): {c['note']}", tags))

for e in load("auth_events.csv"):
    if e["user_id"] != subject:
        continue
    tags = []
    if e["host"].startswith("WS-") and e["host"] not in known_hosts:
        tags.append("Unregistered host")
    if e["result"] == "FAILURE":
        tags.append("Failed login")
    events.append((e["ts"], e["source"], f"{e['event']} {e['result']} from {e['host']}", tags))

for a in load("billing_adjustments.csv"):
    if a["initiator_user_id"] != subject or a["approver_user_id"] != subject:
        continue
    t = datetime.fromisoformat(a["initiated_ts"])
    tags = ["Self-approved"]
    if t.weekday() >= 5 or not 7 <= t.hour < 19:
        tags.append("Off-hours")
    if (t - grant_ts).total_seconds() < 72 * 3600:
        tags.append("Within 72h of role grant")
    events.append((a["initiated_ts"], "Billing adjustment",
                   f"{a['txn_id']} ${float(a['amount']):,.2f} to {a['customer_account']} ({a['reason_code']})", tags))

events.sort(key=lambda x: x[0])
with open(OUT / "incident_timeline.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp", "source", "event", "detection_conditions"])
    for ts, src, ev, tags in events:
        w.writerow([ts, src, ev, "; ".join(tags)])
print(f"Subject {subject}: {len(events)} events written to output/incident_timeline.csv")
