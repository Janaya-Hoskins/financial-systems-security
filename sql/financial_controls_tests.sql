-- Financial systems control tests (synthetic Northwind Holdings data)
-- Table names match the CSV files in /data. Load them into any SQL engine
-- as tables of the same name to run these queries. Date functions use SQLite syntax;
-- swap in your engine's equivalents (DATEDIFF, EXTRACT) for Postgres or Snowflake.

-- 1. Terminated employees with active application accounts (APD-02)
SELECT a.user_id, h.first_name, h.last_name, h.department, h.termination_date,
       CAST(JULIANDAY('2025-12-31') - JULIANDAY(h.termination_date) AS INTEGER) AS days_active_after_termination
FROM system_accounts a
JOIN hr_roster h ON h.employee_id = a.employee_id
WHERE a.status = 'Active'
  AND h.status = 'Terminated';

-- 2. Transfers that kept prior-department roles (APD-03)
SELECT a.user_id, h.prior_department, h.department, h.transfer_date, r.role_code
FROM hr_roster h
JOIN system_accounts a  ON a.employee_id = h.employee_id
JOIN role_assignments r ON r.user_id = a.user_id
JOIN role_catalog c     ON c.role_code = r.role_code
WHERE h.transfer_date <> ''
  AND c.home_department = h.prior_department;

-- 3. Accounts with no HR owner that are not documented service accounts (APD-08)
SELECT a.user_id, a.account_type, a.created_date, a.last_login
FROM system_accounts a
LEFT JOIN hr_roster h ON h.employee_id = a.employee_id
WHERE h.employee_id IS NULL
  AND a.account_type <> 'Service';

-- 4. Access-level SoD conflicts across all of a person's accounts (APD-07)
WITH person_roles AS (
  SELECT COALESCE(NULLIF(a.employee_id, ''), a.user_id) AS person_key, r.role_code
  FROM role_assignments r
  JOIN system_accounts a ON a.user_id = r.user_id
)
SELECT p1.person_key, s.role_a, s.role_b, s.rating, s.risk
FROM sod_rules s
JOIN person_roles p1 ON p1.role_code = s.role_a
JOIN person_roles p2 ON p2.role_code = s.role_b AND p2.person_key = p1.person_key
ORDER BY s.rating, p1.person_key;

-- 5. Transaction-level SoD: adjustments initiated and approved by the same person,
--    including through a second account the person owns
SELECT b.txn_id, b.initiated_ts, b.amount, b.initiator_user_id, b.approver_user_id,
       CASE WHEN b.initiator_user_id = b.approver_user_id THEN 'Same account'
            ELSE 'Same person, second account' END AS breach_type
FROM billing_adjustments b
JOIN system_accounts ai ON ai.user_id = b.initiator_user_id
JOIN system_accounts ap ON ap.user_id = b.approver_user_id
WHERE b.initiator_user_id = b.approver_user_id
   OR (ai.employee_id <> '' AND ai.employee_id = ap.employee_id)
ORDER BY b.initiated_ts;

-- 6. Emergency grants with no expiry (APD-06)
SELECT ts, user_id, role_code, changed_by, ticket, note
FROM role_change_log
WHERE action = 'GRANT' AND (expiry IS NULL OR expiry = '');

-- 7. Detection logic behind alert FIN-ADJ-07 (CO-02):
--    self-approved adjustment, outside 07:00-19:00 or on a weekend,
--    within 72 hours of the approver receiving the approval role
SELECT b.txn_id, b.initiated_ts, b.amount, b.customer_account, rc.ticket AS role_grant_ticket
FROM billing_adjustments b
JOIN role_change_log rc
  ON rc.user_id = b.approver_user_id AND rc.action = 'GRANT' AND rc.role_code = 'ADJ_APPR'
WHERE b.initiator_user_id = b.approver_user_id
  AND (CAST(STRFTIME('%H', b.initiated_ts) AS INTEGER) NOT BETWEEN 7 AND 18
       OR STRFTIME('%w', b.initiated_ts) IN ('0', '6'))
  AND (JULIANDAY(b.initiated_ts) - JULIANDAY(rc.ts)) * 24 <= 72;

-- Equivalent Splunk SPL for FIN-ADJ-07 (field names illustrative)
-- index=fin_apps sourcetype=billing:adjustment
-- | where initiator_user_id=approver_user_id
-- | eval hour=strftime(_time,"%H"), dow=strftime(_time,"%w")
-- | where hour<7 OR hour>=19 OR dow IN ("0","6")
-- | join type=inner approver_user_id
--     [ search index=iam sourcetype=role_change action=GRANT role_code=ADJ_APPR earliest=-72h
--       | rename user_id AS approver_user_id | fields approver_user_id ticket ]
-- | stats count sum(amount) AS total values(customer_account) AS accounts BY approver_user_id ticket
