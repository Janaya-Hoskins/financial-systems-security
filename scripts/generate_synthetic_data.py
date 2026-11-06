"""Generate the synthetic dataset used throughout this repository.

Every record is fictional. "Northwind Holdings" is an invented company, and every
person, account and transaction is generated here with a fixed random seed so the
outputs are reproducible. Specific exceptions are seeded on purpose so the testing
scripts have something realistic to find.

Run from the repository root:
    python scripts/generate_synthetic_data.py
"""
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

random.seed(20251231)
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
AS_OF = date(2025, 12, 31)

FIRST = ["Avery", "Blake", "Casey", "Dana", "Elliot", "Frankie", "Gray", "Harper", "Indy", "Jordan",
         "Kai", "Logan", "Morgan", "Noel", "Oakley", "Parker", "Quinn", "Reese", "Sage", "Tatum",
         "Umi", "Val", "Wren", "Xen", "Yael", "Zion", "Ari", "Bryn", "Cruz", "Drew"]
LAST = ["Abbott", "Bishop", "Calloway", "Dunmore", "Ellery", "Fairbanks", "Garnett", "Holloway",
        "Ingram", "Jessup", "Kingsley", "Lockhart", "Merriwether", "Northcott", "Oakes", "Pembrook",
        "Quill", "Radcliffe", "Sterling", "Thorne", "Underhill", "Vance", "Whitlock", "Yardley"]

DEPTS = {
    "Billing Operations": ["BILL_SETUP", "ADJ_INIT"],
    "Billing Supervision": ["ADJ_APPR"],
    "Accounts Receivable": ["PAY_APPLY"],
    "Credit & Collections": ["AR_WRITEOFF"],
    "General Ledger": ["GL_POST"],
    "Controllership": ["GL_APPR"],
    "Accounts Payable": ["AP_PAY"],
    "Procurement": ["VENDOR_MAINT"],
    "IT Application Support": ["SYS_ADMIN"],
    "Information Security": ["SEC_ADMIN"],
    "Internal Audit": ["AUDIT_READ"],
}
HEADCOUNT = {"Billing Operations": 34, "Billing Supervision": 8, "Accounts Receivable": 18, "Credit & Collections": 6,
             "General Ledger": 14, "Controllership": 6, "Accounts Payable": 16, "Procurement": 10,
             "IT Application Support": 8, "Information Security": 4, "Internal Audit": 5}
SYSTEM_FOR_ROLE = {"BILL_SETUP": "Billing (Oracle CC&B)", "ADJ_INIT": "Billing (Oracle CC&B)",
                   "ADJ_APPR": "Billing (Oracle CC&B)", "PAY_APPLY": "ERP (SAP FI/CO)",
                   "AR_WRITEOFF": "ERP (SAP FI/CO)", "GL_POST": "ERP (SAP FI/CO)",
                   "GL_APPR": "ERP (SAP FI/CO)", "AP_PAY": "ERP (SAP FI/CO)",
                   "VENDOR_MAINT": "ERP (SAP FI/CO)", "SYS_ADMIN": "Billing (Oracle CC&B)",
                   "SEC_ADMIN": "ERP (SAP FI/CO)", "AUDIT_READ": "ERP (SAP FI/CO)"}

used = set()


def person_name():
    while True:
        n = (random.choice(FIRST), random.choice(LAST))
        if n not in used:
            used.add(n)
            return n


def rand_date(start, end):
    return start + timedelta(days=random.randint(0, (end - start).days))


hr, users, grants = [], [], []
emp_no = 1000
uid_by_emp = {}
for dept, n in HEADCOUNT.items():
    for _ in range(n):
        emp_no += 1
        f, l = person_name()
        eid = f"E{emp_no}"
        hr.append({"employee_id": eid, "first_name": f, "last_name": l, "department": dept,
                   "status": "Active", "hire_date": rand_date(date(2015, 1, 1), date(2024, 12, 31)).isoformat(),
                   "termination_date": "", "transfer_date": "", "prior_department": ""})
        uid = base = f"{f[0].lower()}.{l.lower()}"
        k = 2
        while uid in uid_by_emp.values():  # keep account IDs unique per person
            uid, k = f"{base}{k}", k + 1
        uid_by_emp[eid] = uid
        users.append({"user_id": uid, "employee_id": eid, "account_type": "Privileged" if dept in ("IT Application Support", "Information Security") else "Standard",
                      "status": "Active", "created_date": hr[-1]["hire_date"],
                      "last_login": rand_date(date(2025, 11, 1), AS_OF).isoformat()})
        for role in DEPTS[dept]:
            grants.append({"user_id": uid, "role_code": role, "system": SYSTEM_FOR_ROLE[role],
                           "granted_date": hr[-1]["hire_date"], "approval_ticket": f"REQ-{random.randint(10000, 99999)}"})

by_dept = {}
for h in hr:
    by_dept.setdefault(h["department"], []).append(h)

# --- Seeded exceptions -------------------------------------------------------
# 1) Terminated employees whose accounts remain active
for h in random.sample(by_dept["Billing Operations"], 2) + random.sample(by_dept["Accounts Payable"], 1):
    h["status"] = "Terminated"
    h["termination_date"] = rand_date(date(2025, 8, 1), date(2025, 10, 31)).isoformat()

# 2) Transfers whose old access was never removed
for src, dst in [("Billing Operations", "Billing Supervision"), ("Accounts Receivable", "General Ledger")]:
    h = random.choice([x for x in by_dept[src] if x["status"] == "Active"])
    h["prior_department"], h["department"] = src, dst
    h["transfer_date"] = rand_date(date(2025, 6, 1), date(2025, 9, 30)).isoformat()
    for role in DEPTS[dst]:
        grants.append({"user_id": uid_by_emp[h["employee_id"]], "role_code": role, "system": SYSTEM_FOR_ROLE[role],
                       "granted_date": h["transfer_date"], "approval_ticket": f"REQ-{random.randint(10000, 99999)}"})

# 3) Orphaned accounts with no HR record
for uid, role in [("p.contractor7", "PAY_APPLY"), ("temp.glsupport", "GL_POST")]:
    users.append({"user_id": uid, "employee_id": "", "account_type": "Standard", "status": "Active",
                  "created_date": "2024-03-11", "last_login": "2025-07-02"})
    grants.append({"user_id": uid, "role_code": role, "system": SYSTEM_FOR_ROLE[role], "granted_date": "2024-03-11",
                   "approval_ticket": ""})

# 4) Service account used by the nightly billing batch (expected; documented as mitigated)
users.append({"user_id": "svc_billing_batch", "employee_id": "", "account_type": "Service", "status": "Active",
              "created_date": "2019-05-01", "last_login": "2025-12-31"})
grants.append({"user_id": "svc_billing_batch", "role_code": "BILL_SETUP", "system": SYSTEM_FOR_ROLE["BILL_SETUP"],
               "granted_date": "2019-05-01", "approval_ticket": "REQ-SVC-001"})

# 5) One employee with a second, privileged account that can also approve adjustments
dual = random.choice(by_dept["Billing Operations"])
dual_uid = uid_by_emp[dual["employee_id"]] + "_adm"
users.append({"user_id": dual_uid, "employee_id": dual["employee_id"], "account_type": "Privileged", "status": "Active",
              "created_date": "2025-02-14", "last_login": "2025-12-19"})
grants.append({"user_id": dual_uid, "role_code": "ADJ_APPR", "system": SYSTEM_FOR_ROLE["ADJ_APPR"],
               "granted_date": "2025-02-14", "approval_ticket": ""})

# 6) Direct SoD conflicts on single accounts
conflicts = [("Procurement", "AP_PAY"), ("General Ledger", "GL_APPR"), ("IT Application Support", "ADJ_APPR"),
             ("Accounts Receivable", "AR_WRITEOFF")]
for dept, role in conflicts:
    h = random.choice([x for x in by_dept[dept] if x["status"] == "Active" and not x["transfer_date"]])
    grants.append({"user_id": uid_by_emp[h["employee_id"]], "role_code": role, "system": SYSTEM_FOR_ROLE[role],
                   "granted_date": rand_date(date(2025, 1, 1), date(2025, 9, 30)).isoformat(),
                   "approval_ticket": f"REQ-{random.randint(10000, 99999)}"})

# 7) Incident subject: billing analyst granted emergency approval rights with no expiry
subject = random.choice([x for x in by_dept["Billing Operations"] if x["status"] == "Active" and not x["transfer_date"] and x is not dual])
subject_uid = uid_by_emp[subject["employee_id"]]
grants.append({"user_id": subject_uid, "role_code": "ADJ_APPR", "system": SYSTEM_FOR_ROLE["ADJ_APPR"],
               "granted_date": "2025-10-17", "approval_ticket": "EA-0412 (emergency)"})

# --- Billing adjustments, Q3-Q4 2025 ------------------------------------------
init_pool = [uid_by_emp[h["employee_id"]] for h in by_dept["Billing Operations"] if h["status"] == "Active" and not h["transfer_date"]]
appr_pool = [uid_by_emp[h["employee_id"]] for h in by_dept["Billing Supervision"] if not h["transfer_date"]]
mover = next(h for h in hr if h["prior_department"] == "Billing Operations")
mover_uid = uid_by_emp[mover["employee_id"]]
adj = []
n = 0


def add_adj(ts, amount, init, appr, reason):
    global n
    n += 1
    adj.append({"txn_id": f"ADJ-25-{n:05d}", "initiated_ts": ts.isoformat(sep=" "), "approved_ts": (ts + timedelta(minutes=random.randint(3, 600))).isoformat(sep=" "),
                "amount": f"{amount:.2f}", "initiator_user_id": init, "approver_user_id": appr,
                "customer_account": f"CA-{random.randint(100000, 999999)}", "reason_code": reason})


for _ in range(2400):
    d = rand_date(date(2025, 7, 1), date(2025, 12, 31))
    ts = datetime(d.year, d.month, d.day, random.randint(8, 17), random.randint(0, 59))
    amt = round(random.lognormvariate(6.2, 1.3), 2)
    add_adj(ts, min(amt, 250000), random.choice(init_pool), random.choice(appr_pool),
            random.choice(["RATE_CORRECTION", "METER_ESTIMATE", "DUPLICATE_CHARGE", "GOODWILL", "CANCEL_REBILL"]))

# Seeded SoD breaches in the transaction log
# Transferred supervisor who kept initiation rights self-approves after the move
mv = date.fromisoformat(mover["transfer_date"])
for days, amt in [(9, 23450.00), (37, 4120.50), (71, 980.00)]:
    d = mv + timedelta(days=days)
    add_adj(datetime(d.year, d.month, d.day, 14, 5), amt, mover_uid, mover_uid, "CANCEL_REBILL")
add_adj(datetime(2025, 9, 3, 10, 44), 11200.00, uid_by_emp[dual["employee_id"]], dual_uid, "RATE_CORRECTION")

# Incident transactions: off-hours, self-approved, Saturday 2025-10-18
inc_accts = ["CA-482211", "CA-482219", "CA-517730"]
for i, amt in enumerate([9800.00, 7450.00, 9900.00, 6200.00, 8150.00, 6800.00]):
    n += 1
    t0 = datetime(2025, 10, 18, 23, 20) + timedelta(minutes=5 * i)
    adj.append({"txn_id": f"ADJ-25-{n:05d}", "initiated_ts": t0.isoformat(sep=" "),
                "approved_ts": (t0 + timedelta(minutes=1)).isoformat(sep=" "), "amount": f"{amt:.2f}",
                "initiator_user_id": subject_uid, "approver_user_id": subject_uid,
                "customer_account": inc_accts[i % 3], "reason_code": "GOODWILL"})

# --- Incident telemetry --------------------------------------------------------
role_changes = [
    {"ts": "2025-10-17 16:05:00", "user_id": subject_uid, "role_code": "ADJ_APPR", "action": "GRANT",
     "changed_by": "helpdesk.tier2", "ticket": "EA-0412", "expiry": "", "note": "Emergency access: month-end backlog"},
    {"ts": "2025-10-19 08:15:00", "user_id": subject_uid, "role_code": "ADJ_APPR", "action": "REVOKE",
     "changed_by": "iam.ops", "ticket": "INC-77031", "expiry": "", "note": "Revoked during incident response"},
]
auth = [
    {"ts": "2025-10-18 23:09:41", "user_id": subject_uid, "source": "VPN", "host": "WS-UNREG-77", "event": "LOGIN", "result": "SUCCESS"},
    {"ts": "2025-10-18 23:12:02", "user_id": subject_uid, "source": "Billing (Oracle CC&B)", "host": "WS-UNREG-77", "event": "LOGIN", "result": "FAILURE"},
    {"ts": "2025-10-18 23:12:40", "user_id": subject_uid, "source": "Billing (Oracle CC&B)", "host": "WS-UNREG-77", "event": "LOGIN", "result": "FAILURE"},
    {"ts": "2025-10-18 23:14:05", "user_id": subject_uid, "source": "Billing (Oracle CC&B)", "host": "WS-UNREG-77", "event": "LOGIN", "result": "SUCCESS"},
    {"ts": "2025-10-18 23:52:30", "user_id": subject_uid, "source": "Billing (Oracle CC&B)", "host": "WS-UNREG-77", "event": "LOGOUT", "result": "SUCCESS"},
    {"ts": "2025-10-19 07:30:00", "user_id": subject_uid, "source": "SIEM", "host": "siem-01", "event": "ALERT FIN-ADJ-07", "result": "TRIGGERED"},
]
assets = [{"host": f"WS-BILL-{i:03d}", "assigned_department": "Billing Operations"} for i in range(1, 41)]


def write(name, rows):
    with open(DATA / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


write("hr_roster.csv", hr)
write("system_accounts.csv", users)
write("role_assignments.csv", grants)
write("billing_adjustments.csv", adj)
write("role_change_log.csv", role_changes)
write("auth_events.csv", auth)
write("asset_inventory.csv", assets)

sod_rules = [
    ("ADJ_INIT", "ADJ_APPR", "Prohibited", "Initiate and approve the same billing adjustment"),
    ("GL_POST", "GL_APPR", "Prohibited", "Post and approve the same journal entry"),
    ("VENDOR_MAINT", "AP_PAY", "Prohibited", "Create a vendor and release payment to it"),
    ("SYS_ADMIN", "ADJ_APPR", "Prohibited", "Administer the billing system and approve adjustments in it"),
    ("SEC_ADMIN", "GL_APPR", "Prohibited", "Grant access and approve journal entries"),
    ("AUDIT_READ", "GL_POST", "Prohibited", "Post entries and review them as auditor"),
    ("PAY_APPLY", "AR_WRITEOFF", "Mitigating control", "Apply payments and write off the remaining balance"),
    ("BILL_SETUP", "ADJ_APPR", "Mitigating control", "Set up billing terms and approve adjustments against them"),
    ("PAY_APPLY", "GL_POST", "Mitigating control", "Apply cash and post the related journal"),
]
write("sod_rules.csv", [{"role_a": a, "role_b": b, "rating": r, "risk": d} for a, b, r, d in sod_rules])
write("role_catalog.csv", [{"role_code": r, "system": SYSTEM_FOR_ROLE[r], "home_department": next(d for d, rs in DEPTS.items() if r in rs)} for r in SYSTEM_FOR_ROLE])
print(f"HR {len(hr)} | accounts {len(users)} | role grants {len(grants)} | adjustments {len(adj)}")
