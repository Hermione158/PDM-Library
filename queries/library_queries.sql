-- =====================================================================
--  PDM Library — useful SQLite queries
--  Run these against library.db (the live one at the project root, or
--  the copy beside PDM-Library.exe on the library PC).
--
--  HOW TO USE
--    DB Browser for SQLite : Open Database -> library.db -> Execute SQL
--    Command line          : sqlite3 library.db < library_queries.sql
--
--  BEFORE YOU WRITE (not just read):
--    1. close PDM-Library.exe — it holds the database open
--    2. copy library.db somewhere safe first (that copy IS a full backup)
--  Read-only exploration is always safe.
--
--  NOTE: the retired demo student accounts (2024-01842 etc.) no longer
--  exist. Where an example needed a student number, use YOURS.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. WHO IS WHO
-- ---------------------------------------------------------------------

-- Every account, with its current state.
SELECT username, name, role, program, year_level, section, status, joined
FROM users
ORDER BY role, username;

-- Staff and administrator accounts only.
SELECT username, name, role, status
FROM users
WHERE role IN ('staff', 'admin')
ORDER BY role, username;

-- Students with anything currently on loan, or anything overdue.
SELECT
    u.username,
    u.name,
    u.program,
    u.status AS account_status,
    COUNT(CASE WHEN l.status = 'overdue' THEN 1 END) AS overdue_now,
    COUNT(CASE WHEN l.status = 'active'  THEN 1 END) AS on_loan,
    MAX(l.due_date) AS latest_due_date
FROM users u
JOIN loans l ON l.user_id = u.id
WHERE l.status IN ('active', 'overdue') AND u.role = 'student'
GROUP BY u.id
ORDER BY overdue_now DESC, u.username;


-- ---------------------------------------------------------------------
-- 2. OVERDUE / COLLECTIONS
-- ---------------------------------------------------------------------

-- Everything overdue right now: who, which book, how many days late.
-- This is the working list for chasing borrowers.
SELECT
    u.username,
    u.name,
    b.title,
    c.accession,
    c.shelf,
    l.due_date,
    CAST(julianday('now') - julianday(l.due_date) AS INTEGER) AS days_overdue,
    u.status AS account_status
FROM loans l
JOIN users  u ON u.id = l.user_id
JOIN copies c ON c.id = l.copy_id
JOIN books  b ON b.id = c.book_id
WHERE l.status = 'overdue'
ORDER BY days_overdue DESC;

-- Students who will be escalated to the SDO soon (1 day overdue = final
-- warning; 2+ days = case opened and account restricted).
SELECT
    u.name,
    u.username,
    b.title,
    CAST(julianday('now') - julianday(l.due_date) AS INTEGER) AS days_overdue
FROM loans l
JOIN users  u ON u.id = l.user_id
JOIN copies c ON c.id = l.copy_id
JOIN books  b ON b.id = c.book_id
WHERE l.status IN ('active', 'overdue')
  AND l.due_date <= date('now')
  AND u.status = 'active'
ORDER BY days_overdue DESC;

-- Students barred from borrowing (blocked) and why they still are.
SELECT
    u.name,
    u.username,
    COUNT(CASE WHEN l.status = 'overdue' THEN 1 END) AS overdue_now,
    (SELECT COUNT(*) FROM sdo_cases s
      WHERE s.user_id = u.id AND s.status = 'pending') AS pending_sdo_cases
FROM users u
LEFT JOIN loans l ON l.user_id = u.id
WHERE u.status = 'blocked'
GROUP BY u.id
ORDER BY pending_sdo_cases DESC, u.username;


-- ---------------------------------------------------------------------
-- 3. SDO / DISCIPLINE REGISTER
-- ---------------------------------------------------------------------

-- The full escalation register, newest first, with how each case closed.
-- closed_by = 'sdo'   -> admin recorded an SDO receipt
-- closed_by = NULL    -> closed before the receipt feature existed
SELECT
    'SDO-' || printf('%03d', s.id) AS case_id,
    u.username,
    u.name,
    b.title,
    l.due_date,
    CAST(julianday('now') - julianday(l.due_date) AS INTEGER) AS days_overdue,
    s.status,
    s.closed_by,
    s.receipt_ref,
    s.created_at,
    s.resolved_at
FROM sdo_cases s
JOIN users  u ON u.id = s.user_id
JOIN loans  l ON l.id = s.loan_id
JOIN copies c ON c.id = l.copy_id
JOIN books  b ON b.id = c.book_id
ORDER BY CASE s.status WHEN 'pending' THEN 0 ELSE 1 END, s.id DESC;

-- Pending cases only — the administrator's to-do list.
SELECT
    'SDO-' || printf('%03d', s.id) AS case_id,
    u.name, u.username,
    b.title,
    CAST(julianday('now') - julianday(l.due_date) AS INTEGER) AS days_overdue,
    s.created_at AS opened
FROM sdo_cases s
JOIN users  u ON u.id = s.user_id
JOIN loans  l ON l.id = s.loan_id
JOIN copies c ON c.id = l.copy_id
JOIN books  b ON b.id = c.book_id
WHERE s.status = 'pending'
ORDER BY s.id;

-- Receipt audit trail: which student presented which SDO receipt.
SELECT receipt_ref, COUNT(*) AS uses, GROUP_CONCAT(u.name, ', ') AS students
FROM sdo_cases s
JOIN users u ON u.id = s.user_id
WHERE s.receipt_ref IS NOT NULL
GROUP BY s.receipt_ref
ORDER BY uses DESC, receipt_ref;


-- ---------------------------------------------------------------------
-- 4. CATALOG / INVENTORY
-- ---------------------------------------------------------------------

-- Full catalog with live availability per title.
SELECT
    b.id,
    b.title,
    b.author,
    b.category,
    c.shelf,
    COUNT(*)                                                    AS copies,
    SUM(CASE WHEN c.status = 'available'   THEN 1 ELSE 0 END)  AS on_shelf,
    SUM(CASE WHEN c.status = 'checked_out' THEN 1 ELSE 0 END)  AS checked_out,
    SUM(CASE WHEN c.status = 'reserved'    THEN 1 ELSE 0 END)  AS reserved
FROM books b
JOIN copies c ON c.book_id = b.id
GROUP BY b.id
ORDER BY b.title;

-- Titles with nothing available, and why.
SELECT
    b.title,
    SUM(CASE WHEN c.status = 'checked_out' THEN 1 ELSE 0 END) AS on_loan,
    SUM(CASE WHEN c.status = 'reserved'    THEN 1 ELSE 0 END) AS held_for_pickup,
    (SELECT COUNT(*) FROM reservations r
      WHERE r.book_id = b.id AND r.status = 'waiting')        AS waiting
FROM books b
JOIN copies c ON c.book_id = b.id
GROUP BY b.id
HAVING SUM(CASE WHEN c.status = 'available' THEN 1 ELSE 0 END) = 0
ORDER BY waiting DESC, b.title;

-- HEALTH CHECK — "stuck" copies. Both branches should return 0 rows.
-- (a) checked out with no loan row behind it: shows as checked out forever
--     with nothing that can bring it back.
SELECT c.accession, b.title, c.status AS flagged_status, 'no loan row' AS why
FROM copies c
JOIN books b ON b.id = c.book_id
WHERE c.status = 'checked_out'
  AND c.id NOT IN (SELECT copy_id FROM loans WHERE status IN ('active', 'overdue'))
UNION ALL
-- (b) reserved for pickup but the hold no longer exists (reservations track a
--     book_id, not a copy_id, so this is checked at title level).
SELECT c.accession, b.title, c.status, 'no matching hold' AS why
FROM copies c
JOIN books b ON b.id = c.book_id
WHERE c.status = 'reserved'
  AND b.id NOT IN (SELECT book_id FROM reservations
                   WHERE status IN ('requested', 'ready'));

-- Same idea for loans: a loan row with no matching copy status.
SELECT l.id, c.accession, b.title, l.status, c.status AS copy_status
FROM loans l
JOIN copies c ON c.id = l.copy_id
JOIN books  b ON b.id = c.book_id
WHERE l.status IN ('active', 'overdue') AND c.status <> 'checked_out';


-- ---------------------------------------------------------------------
-- 5. CIRCULATION ACTIVITY
-- ---------------------------------------------------------------------

-- Circulation totals per day for the last 30 days (checkouts vs returns).
SELECT
    date(ts) AS day,
    SUM(CASE WHEN type = 'Checkout' THEN 1 ELSE 0 END) AS checkouts,
    SUM(CASE WHEN type = 'Return'   THEN 1 ELSE 0 END) AS returns,
    SUM(CASE WHEN type = 'Renewal'  THEN 1 ELSE 0 END) AS renewals
FROM transactions
WHERE ts >= date('now', '-30 days')
GROUP BY date(ts)
ORDER BY day DESC;

-- Busiest titles.
SELECT
    b.title,
    COUNT(*) AS times_lent
FROM transactions t
JOIN copies c ON c.id = t.copy_id
JOIN books  b ON b.id = c.book_id
WHERE t.type = 'Checkout'
GROUP BY b.id
ORDER BY times_lent DESC, b.title
LIMIT 20;

-- Staff activity (who processed what).
SELECT
    s.name AS processed_by,
    s.role,
    COUNT(t.id) AS events,
    SUM(CASE WHEN t.type = 'Checkout' THEN 1 ELSE 0 END) AS checkouts,
    SUM(CASE WHEN t.type = 'Return'   THEN 1 ELSE 0 END) AS returns
FROM transactions t
JOIN users s ON s.id = t.staff_id
GROUP BY s.id
ORDER BY events DESC;

-- Full audit trail for one student — REPLACE with a real student number,
-- e.g. (SELECT username FROM users WHERE role='student' LIMIT 1).
SELECT
    t.ts,
    t.type,
    b.title,
    c.accession,
    t.status,
    t.note,
    st.name AS processed_by
FROM transactions t
JOIN users  u  ON u.id  = t.user_id
LEFT JOIN users st ON st.id = t.staff_id
LEFT JOIN copies c ON c.id = t.copy_id
LEFT JOIN books  b ON b.id = c.book_id
WHERE u.username = (SELECT username FROM users WHERE role='student' LIMIT 1)
ORDER BY t.ts DESC;


-- ---------------------------------------------------------------------
-- 6. HOLDS AND WAITLISTS
-- ---------------------------------------------------------------------

-- Current reservation queue per title.
SELECT
    b.title,
    u.name,
    u.username,
    CASE r.status
        WHEN 'requested' THEN 'Borrow requested'
        WHEN 'waiting'   THEN 'Waiting'
        WHEN 'ready'     THEN 'Ready for pickup'
    END AS state,
    r.position,
    r.created_at,
    r.ready_at
FROM reservations r
JOIN users u ON u.id = r.user_id
JOIN books b ON b.id = r.book_id
ORDER BY b.id, CASE r.status WHEN 'requested' THEN 0 WHEN 'ready' THEN 1 ELSE 2 END,
         r.position;

-- Holds whose pickup deadline has passed (the next scan will expire these).
SELECT
    u.name,
    b.title,
    r.ready_at AS deadline,
    CAST(julianday('now') - julianday(r.ready_at) AS INTEGER) AS days_overdue
FROM reservations r
JOIN users u ON u.id = r.user_id
JOIN books b ON b.id = r.book_id
WHERE r.status = 'ready' AND r.ready_at < date('now');


-- ---------------------------------------------------------------------
-- 7. NOTIFICATIONS
-- ---------------------------------------------------------------------

-- Unread system-wide notices (what the dashboard feed shows).
SELECT ts, title, body, level
FROM notifications
WHERE user_id IS NULL AND read = 0
ORDER BY ts DESC;

-- Everything sent to the first student on file.
SELECT ts, title, body, level
FROM notifications
WHERE user_id = (SELECT id FROM users WHERE role='student' LIMIT 1)
ORDER BY ts DESC
LIMIT 30;

-- Password reset / change trail (audit of desk credential activity).
SELECT ts, u.username, u.name, title, body
FROM notifications n
LEFT JOIN users u ON u.id = n.user_id
WHERE n.title IN ('Password reset', 'Password changed')
ORDER BY ts DESC;


-- ---------------------------------------------------------------------
-- 8. SETTINGS AND HOUSEKEEPING
-- ---------------------------------------------------------------------

-- Current policy values (the app re-seeds these from the constants on launch).
SELECT key, value FROM settings ORDER BY key;

-- Row counts — a quick "is anything missing?" check.
SELECT 'books'        AS table_name, COUNT(*) AS rows FROM books
UNION ALL SELECT 'copies',       COUNT(*) FROM copies
UNION ALL SELECT 'users',        COUNT(*) FROM users
UNION ALL SELECT 'loans',        COUNT(*) FROM loans
UNION ALL SELECT 'reservations', COUNT(*) FROM reservations
UNION ALL SELECT 'transactions', COUNT(*) FROM transactions
UNION ALL SELECT 'notifications',COUNT(*) FROM notifications
UNION ALL SELECT 'sdo_cases',    COUNT(*) FROM sdo_cases;

-- Integrity check. Should return no rows.
PRAGMA foreign_key_check;

-- Reclaim space after deleting a lot (run with the app closed).
-- VACUUM;