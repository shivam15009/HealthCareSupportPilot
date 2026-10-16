import argparse
import shutil
import sqlite3
from datetime import date, timedelta, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TICKETS_DB = ROOT / "healthcare_support.db"
USERS_DB = ROOT / "users.db"

parser = argparse.ArgumentParser()
parser.add_argument(
    "--apply",
    action="store_true",
    help="Back up databases and apply cleanup after confirmation",
)
args = parser.parse_args()

for path in (TICKETS_DB, USERS_DB):
    if not path.is_file():
        raise SystemExit(f"Database not found: {path}")

today = date.today()
start_date = (today - timedelta(days=1)).isoformat()
end_date = today.isoformat()

def retained_ticket_ids(con):
    return {
        row[0] for row in con.execute("""
            SELECT ticket_id
            FROM support_tickets
            WHERE created_at IS NOT NULL
              AND substr(created_at, 1, 10) BETWEEN ? AND ?
        """, (start_date, end_date))
    }

# Check the expected schema before proceeding.
with sqlite3.connect(TICKETS_DB) as con:
    tables = {
        row[0] for row in con.execute("""
            SELECT name FROM sqlite_master WHERE type='table'
        """)
    }
    required = {
        "support_tickets",
        "ai_resolution_attempts",
        "ticket_classification_events",
        "ticket_multiagent_runs",
        "ticket_validation_events",
    }
    if not required.issubset(tables):
        raise SystemExit(
            f"Missing expected ticket tables: {required - tables}. "
            "No changes made."
        )

with sqlite3.connect(USERS_DB) as con:
    if "users" not in {
        row[0] for row in con.execute("""
            SELECT name FROM sqlite_master WHERE type='table'
        """)
    }:
        raise SystemExit("Missing users table. No changes made.")

# Display a preview.
with sqlite3.connect(TICKETS_DB) as con:
    keep_ids = retained_ticket_ids(con)
    total_tickets = con.execute(
        "SELECT COUNT(*) FROM support_tickets"
    ).fetchone()[0]
    related_counts = {}
    for table in (
        "ai_resolution_attempts",
        "ticket_classification_events",
        "ticket_multiagent_runs",
        "ticket_validation_events",
    ):
        related_counts[table] = con.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

with sqlite3.connect(USERS_DB) as con:
    user_total = con.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

with sqlite3.connect(TICKETS_DB) as con:
    referenced_user_ids = {
        row[0] for row in con.execute("""
            SELECT DISTINCT user_id
            FROM support_tickets
            WHERE created_at IS NOT NULL
              AND substr(created_at, 1, 10) BETWEEN ? AND ?
              AND user_id IS NOT NULL
        """, (start_date, end_date))
    }

with sqlite3.connect(USERS_DB) as con:
    if referenced_user_ids:
        placeholders = ",".join("?" for _ in referenced_user_ids)
        users_to_keep = con.execute(
            f"SELECT COUNT(*) FROM users WHERE id IN ({placeholders})",
            tuple(referenced_user_ids),
        ).fetchone()[0]
    else:
        users_to_keep = 0

print(f"Date range: {start_date} through {end_date} (inclusive)")
print(f"Tickets: {total_tickets}; retain {len(keep_ids)}; "
      f"delete {total_tickets - len(keep_ids)}")
print(f"Users: {user_total}; retain {users_to_keep}; "
      f"delete {user_total - users_to_keep}")
print("Related records currently present:")
for table, count in related_counts.items():
    print(f"  {table}: {count}")

if not args.apply:
    print("\nDRY RUN ONLY — nothing was deleted.")
    print("After reviewing the results, run: python cleanup_db.py --apply")
    raise SystemExit(0)

if not keep_ids:
    raise SystemExit("No tickets match the date range. Aborting.")

confirmation = input(
    "\nType DELETE to back up both databases and continue: "
)
if confirmation != "DELETE":
    raise SystemExit("Cancelled. Nothing was deleted.")

# Back up both databases before modifying either.
backup_dir = ROOT / (
    "db_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")
)
backup_dir.mkdir()
shutil.copy2(TICKETS_DB, backup_dir / TICKETS_DB.name)
shutil.copy2(USERS_DB, backup_dir / USERS_DB.name)
print(f"Backups created: {backup_dir}")

ticket_con = sqlite3.connect(TICKETS_DB, timeout=30)
user_con = sqlite3.connect(USERS_DB, timeout=30)

try:
    # Confirm backups can be opened and pass SQLite integrity checks.
    for db_path in (
        backup_dir / TICKETS_DB.name,
        backup_dir / USERS_DB.name,
    ):
        with sqlite3.connect(db_path) as check:
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(
                    f"Backup integrity check failed for {db_path.name}: "
                    f"{result}"
                )

    ticket_con.execute("PRAGMA foreign_keys = ON")
    ticket_con.execute("BEGIN IMMEDIATE")
    user_con.execute("BEGIN IMMEDIATE")

    # Recalculate the date-based retention set inside the transaction.
    keep_ids = retained_ticket_ids(ticket_con)
    if not keep_ids:
        raise RuntimeError("No retained tickets found; aborting.")

    # Remove child records for tickets outside the retention window.
    for table in (
        "ai_resolution_attempts",
        "ticket_classification_events",
        "ticket_multiagent_runs",
        "ticket_validation_events",
    ):
        ticket_con.execute(f"""
            DELETE FROM "{table}"
            WHERE ticket_id NOT IN (
                SELECT ticket_id FROM support_tickets
                WHERE created_at IS NOT NULL
                  AND substr(created_at, 1, 10) BETWEEN ? AND ?
            )
        """, (start_date, end_date))

    # Remove old tickets, including NULL or invalid dates.
    ticket_con.execute("""
        DELETE FROM support_tickets
        WHERE created_at IS NULL
           OR substr(created_at, 1, 10) NOT BETWEEN ? AND ?
    """, (start_date, end_date))

    # Keep only accounts referenced by the retained tickets.
    retained_users = {
        row[0] for row in ticket_con.execute("""
            SELECT DISTINCT user_id
            FROM support_tickets
            WHERE user_id IS NOT NULL
        """)
    }

    if retained_users:
        placeholders = ",".join("?" for _ in retained_users)
        user_con.execute(
            f"DELETE FROM users WHERE id NOT IN ({placeholders})",
            tuple(retained_users),
        )
    else:
        user_con.execute("DELETE FROM users")

    # Validate expected ticket count before committing.
    final_tickets = ticket_con.execute(
        "SELECT COUNT(*) FROM support_tickets"
    ).fetchone()[0]
    if final_tickets != len(keep_ids):
        raise RuntimeError(
            f"Ticket count mismatch: expected {len(keep_ids)}, "
            f"found {final_tickets}"
        )

    # Commit both databases; each has its own transaction.
    ticket_con.commit()
    user_con.commit()

    print("\nCleanup completed.")
    print(f"Tickets retained: {final_tickets}")
    print(f"Users retained: {len(retained_users)}")
    print(f"Backup directory: {backup_dir}")

except Exception:
    ticket_con.rollback()
    user_con.rollback()
    print(
        "\nCleanup failed; uncommitted changes were rolled back. "
        "Backups are available if needed."
    )
    raise
finally:
    ticket_con.close()
    user_con.close()
