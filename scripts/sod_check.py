"""Segregation-of-duties testing (synthetic data).

Two tests:
  1. Access-level: does any person hold both roles of a conflicting pair, across all of
     their accounts? Output: output/sod_access_conflicts.csv
  2. Transaction-level: was any billing adjustment initiated and approved by the same
     person (directly, or through a second account they own)?
     Output: output/sod_transaction_breaches.csv

Run from the repository root:
    python scripts/sod_check.py
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "output"
OUT.mkdir(exist_ok=True)


def load(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


hr = {r["employee_id"]: r for r in load("hr_roster.csv")}
accounts = {a["user_id"]: a for a in load("system_accounts.csv")}
rules = load("sod_rules.csv")

# Person key: the HR employee when known, otherwise the account itself
def person(uid):
    return accounts[uid]["employee_id"] or uid

roles_by_person = defaultdict(set)
accts_by_person = defaultdict(set)
for g in load("role_assignments.csv"):
    p = person(g["user_id"])
    roles_by_person[p].add(g["role_code"])
    accts_by_person[p].add(g["user_id"])

access = []
for p, roles in roles_by_person.items():
    for r in rules:
        if r["role_a"] in roles and r["role_b"] in roles:
            owner = hr.get(p)
            access.append({
                "person": f"{owner['first_name']} {owner['last_name']}" if owner else p,
                "department": owner["department"] if owner else "", "accounts": ";".join(sorted(accts_by_person[p])),
                "role_a": r["role_a"], "role_b": r["role_b"], "rating": r["rating"], "risk": r["risk"],
            })
access.sort(key=lambda x: (x["rating"] != "Prohibited", x["person"]))

txn = []
adjustments = load("billing_adjustments.csv")
for a in adjustments:
    same_account = a["initiator_user_id"] == a["approver_user_id"]
    same_person = person(a["initiator_user_id"]) == person(a["approver_user_id"])
    if same_account or same_person:
        txn.append({**a, "breach_type": "Same account" if same_account else "Same person, second account"})
txn.sort(key=lambda x: x["initiated_ts"])

for name, rows in [("sod_access_conflicts.csv", access), ("sod_transaction_breaches.csv", txn)]:
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

total = sum(float(a["amount"]) for a in adjustments)
breach_total = sum(float(t["amount"]) for t in txn)
print(f"People with role grants: {len(roles_by_person)} | access conflicts: {len(access)}")
print(f"Adjustments tested: {len(adjustments)} (${total:,.2f}) | self-approved: {len(txn)} (${breach_total:,.2f})")
