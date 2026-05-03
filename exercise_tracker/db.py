"""Database connection and initialization."""

from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import DATABASE_URL


def get_db():
    """Get a DB connection. Reuses Flask g connection if in request context."""
    try:
        from flask import g, has_app_context
        if has_app_context():
            db = getattr(g, '_db', None)
            if db is None or db.closed:
                g._db = psycopg2.connect(DATABASE_URL)
                g._db.autocommit = True
            return g._db
    except (ImportError, RuntimeError):
        pass
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


@contextmanager
def get_db_transaction():
    """Context manager for transaction blocks: auto-commits on success, rolls back on error.

    Callers may explicitly call conn.rollback() inside the block (e.g. test mode);
    the subsequent auto-commit is then a no-op on the empty transaction.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def close_db(e=None):
    """Close the request-scoped DB connection (called by Flask teardown)."""
    from flask import g
    db = getattr(g, '_db', None)
    if db is not None:
        g._db = None
        if not db.closed:
            db.close()


def update_exercise_freq(code, new_freq):
    """Update target frequency for an exercise in the database.

    Args:
        code: Exercise code (e.g. 'SC')
        new_freq: New frequency as float (0 < freq <= 7)

    Returns:
        (True, name) on success, (False, error_message) on failure.
    """
    if new_freq <= 0 or new_freq > 7:
        return False, "Frequency must be between 0 and 7"

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name FROM exercises WHERE code = %s", (code,))
    row = cur.fetchone()
    if not row:
        return False, f"Unknown exercise code: {code}"
    cur.execute("UPDATE exercises SET target_freq = %s WHERE code = %s", (new_freq, code))
    return True, row[0]


def init_db():
    """Create tables and run migrations.

    Migrations are idempotent (guarded by column/table existence checks)
    so this is safe to call on every app startup.
    """
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS exercises (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                input_type TEXT NOT NULL,
                body_area TEXT
            )
        """)
        # Migration: add body_area column if missing (added after initial schema)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'exercises' AND column_name = 'body_area'
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE exercises ADD COLUMN body_area TEXT")
        # Migration: drop entries table if it still uses the old num1/num2/num3 schema
        # from the prototype — it will be recreated with the current schema below
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'entries' AND column_name = 'num1'
        """)
        if cur.fetchone():
            cur.execute("DROP TABLE entries")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                exercise_code TEXT NOT NULL REFERENCES exercises(code),
                sets TEXT,
                weight NUMERIC(6,2),
                notes TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS exercise_notes (
                exercise_code TEXT PRIMARY KEY REFERENCES exercises(code),
                notes TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS injury_notes (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                notes TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        # Migration: rename mixed-case exercise codes to uppercase for consistency.
        # Early data used e.g. "Bs" instead of "BS"; cascades updates to entries & notes.
        code_renames = [("Bs", "BS"), ("Rs", "RS"), ("Ex", "EX"), ("Gx", "GX"), ("Gy", "GY")]
        for old, new in code_renames:
            cur.execute("SELECT 1 FROM exercises WHERE code = %s", (old,))
            if cur.fetchone():
                cur.execute("UPDATE entries SET exercise_code = %s WHERE exercise_code = %s", (new, old))
                cur.execute("UPDATE exercise_notes SET exercise_code = %s WHERE exercise_code = %s", (new, old))
                cur.execute("DELETE FROM exercises WHERE code = %s", (old,))
        # Migration: add target_freq (times per week) column for planning
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'exercises' AND column_name = 'target_freq'
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE exercises ADD COLUMN target_freq NUMERIC(4,2) DEFAULT 1")
        # Migration: widen target_freq from INTEGER to NUMERIC to support fractional
        # frequencies like 0.5 (once every 2 weeks)
        cur.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'exercises' AND column_name = 'target_freq'
        """)
        col_type = cur.fetchone()
        if col_type and col_type[0] == 'integer':
            cur.execute("ALTER TABLE exercises ALTER COLUMN target_freq TYPE NUMERIC(4,2)")
        # Migration: merge the removed "SS" exercise into "SP" (shoulder press)
        cur.execute("SELECT 1 FROM exercises WHERE code = 'SS'")
        if cur.fetchone():
            cur.execute("UPDATE entries SET exercise_code = 'SP' WHERE exercise_code = 'SS'")
            cur.execute("UPDATE exercise_notes SET exercise_code = 'SP' WHERE exercise_code = 'SS'")
            cur.execute("DELETE FROM exercises WHERE code = 'SS'")
        # Migration: create reminders table for date-based reminders
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                reminder_date DATE NOT NULL,
                text TEXT NOT NULL,
                dismissed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.close()
    finally:
        conn.close()
