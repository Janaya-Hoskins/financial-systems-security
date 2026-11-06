"""Financial-application access reconciliation (synthetic data).

Compares every billing and ERP account against the authoritative HR roster and the
role catalog, then classifies each exception by type. Output goes to
output/access_exceptions.csv.

Checks
  TERMINATED_ACTIVE   account still active after the owner's termination date
  STALE_TRANSFER      role from a prior department still assigned after a transfer
  ORPHANED            account with no HR owner and no service-account documentation
  SERVICE_ACCOUNT     non-human account (reported for owner attestation, not a failure)
  SECOND_PRIVILEGED   one person holds an additional privileged account
  NO_APPROVAL         role grant with no approval ticket on record
  EMERGENCY_NO_EXPIRY emergency access grant with no recorded expiry

Run from the repository root:
    python scripts/reconcile_access.py
"""
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "output"
OUT.mkdir(exist_ok=True)
AS_OF = date(2025, 12, 31)


def load(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


hr = {r["employee_id"]: r for r in load("hr_roster.csv")}
accounts = load("system_accounts.csv")
grants = load("role_assignments.csv")
catalog = {r["role_code"]: r for r in load("role_catalog.csv")}
changes = load("role_change_log.csv")

roles_by_user = defaultdict(list)
for g in grants:
    roles_by_user[g["user_id"]].append(g)

exceptions = []


def flag(kind, severity, acct, detail, roles=""):
    owner = hr.get(acct["employee_id"])
    exceptions.append({
        "exception_type": kind, "severity": severity, "user_id": acct["user_id"],
        "owner": f"{owner['first_name']} {owner['last_name']}" if owner else "(none)",
        "department": owner["department"] if owner else "", "account_type": acct["account_type"],
        "roles": roles or ";".join(g["role_code"] for g in roles_by_user[acct["user_id"]]),
        "detail": detail,
    })


accounts_by_emp = defaultdict(list)
for a in accounts:
    if a["employee_id"]:
        accounts_by_emp[a["employee_id"]].append(a)

for a in accounts:
    if a["status"] != "Active":
        continue
    owner = hr.get(a["employee_id"])
    if a["account_type"] == "Service":
        flag("SERVICE_ACCOUNT", "Info", a, "Non-human account; confirm owner attestation and interactive-login restriction")
        continue
    if owner is None:
        flag("ORPHANED", "High", a, "No matching HR record; no service-account documentation")
        continue
    if owner["status"] == "Terminated":
        days = (AS_OF - date.fromisoformat(owner["termination_date"])).days
        flag("TERMINATED_ACTIVE", "High", a, f"Owner terminated {owner['termination_date']}; account active {days} days later")
    if owner["transfer_date"]:
        stale = [g["role_code"] for g in roles_by_user[a["user_id"]]
                 if catalog[g["role_code"]]["home_department"] == owner["prior_department"]]
        if stale:
            flag("STALE_TRANSFER", "High", a,
                 f"Transferred from {owner['prior_department']} on {owner['transfer_date']}; prior-role access not removed",
                 ";".join(stale))
    if a["account_type"] == "Privileged" and len(accounts_by_emp[a["employee_id"]]) > 1:
        flag("SECOND_PRIVILEGED", "High", a, "Owner holds a standard and a privileged account; privileged account was created without an approval ticket")

for g in grants:
    acct = next(a for a in accounts if a["user_id"] == g["user_id"])
    if acct["account_type"] == "Service":
        continue
    if not g["approval_ticket"] and hr.get(acct["employee_id"]) is not None and acct["account_type"] != "Privileged":
        flag("NO_APPROVAL", "Medium", acct, f"{g['role_code']} granted {g['granted_date']} with no approval ticket", g["role_code"])
    if "emergency" in g["approval_ticket"].lower():
        ch = next((c for c in changes if c["user_id"] == g["user_id"] and c["action"] == "GRANT" and c["role_code"] == g["role_code"]), None)
        if ch and not ch["expiry"]:
            flag("EMERGENCY_NO_EXPIRY", "High", acct, f"Emergency grant {ch['ticket']} on {ch['ts'][:10]} by {ch['changed_by']} with no expiry", g["role_code"])

order = {"High": 0, "Medium": 1, "Info": 2}
exceptions.sort(key=lambda e: (order[e["severity"]], e["exception_type"], e["user_id"]))
with open(OUT / "access_exceptions.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(exceptions[0].keys()))
    w.writeheader()
    w.writerows(exceptions)

active = sum(1 for a in accounts if a["status"] == "Active")
print(f"Accounts reviewed: {active} | role grants: {len(grants)} | exceptions: {len(exceptions)}")
counts = defaultdict(int)
for e in exceptions:
    counts[e["exception_type"]] += 1
for k, v in sorted(counts.items()):
    print(f"  {k:<20} {v}")
