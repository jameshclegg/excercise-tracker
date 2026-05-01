"""Database connection and initialization."""

import re
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import (
    CATEGORY_DEFAULT_INPUT,
    CODE_INPUT_OVERRIDES,
    DATABASE_URL,
    EXERCISES_FILE,
)


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
    """Context manager for transaction blocks. Creates a separate connection with rollback on error."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    try:
        yield conn
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
    """Update target frequency for an exercise in both DB and exercises.txt.

    Args:
        code: Exercise code (e.g. 'SC')
        new_freq: New frequency as float (0 < freq <= 7)

    Returns:
        (True, name) on success, (False, error_message) on failure.
    """
    if new_freq <= 0 or new_freq > 7:
        return False, "Frequency must be between 0 and 7"

    # Format freq for display: use int if whole number, else minimal decimal
    freq_str = f"{new_freq:g}"

    # Update exercises.txt — match the exact code line and replace <N>
    lines = EXERCISES_FILE.read_text().splitlines()
    updated = False
    for i, line in enumerate(lines):
        m = re.match(r"^(" + re.escape(code) + r"\s*=\s*.+?)\s*<[\d.]+>\s*$", line)
        if m:
            lines[i] = f"{m.group(1)} <{freq_str}>"
            updated = True
            break
    if not updated:
        return False, f"Code {code} not found in exercises.txt"

    # Write file, then update DB
    EXERCISES_FILE.write_text("\n".join(lines) + "\n")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE exercises SET target_freq = %s WHERE code = %s", (new_freq, code))
    cur.execute("SELECT name FROM exercises WHERE code = %s", (code,))
    row = cur.fetchone()
    name = row[0] if row else code
    return True, name


def parse_exercises_file():
    """Parse data/exercises.txt into a list of exercise tuples.

    File format per line:
        CODE = Name [category] {body_area} <target_freq>
    where {body_area} and <target_freq> are optional.
    Lines starting with '#' or blank lines are skipped.
    """
    exercises = []
    with open(EXERCISES_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Regex captures: CODE = Name [category] {body_area}? <target_freq>?
            m = re.match(r"^(\S+)\s*=\s*(.+?)\s*\[(\w+)\](?:\s*\{(\w+)\})?(?:\s*<([\d.]+)>)?\s*$", line)
            if m:
                code, name, category = m.group(1), m.group(2).strip(), m.group(3)
                body_area = m.group(4)
                target_freq = float(m.group(5)) if m.group(5) else 1
                input_type = CODE_INPUT_OVERRIDES.get(
                    code, CATEGORY_DEFAULT_INPUT.get(category, "none")
                )
                exercises.append((code, name, category, input_type, body_area, target_freq))
    return exercises


def seed_exercises(cur):
    """Upsert all exercises from the exercises.txt file into the DB.

    Uses ON CONFLICT to update existing rows so the DB always reflects
    the latest definitions without losing referential integrity.
    """
    exercises = parse_exercises_file()
    for code, name, category, input_type, body_area, target_freq in exercises:
        cur.execute(
            """
            INSERT INTO exercises (code, name, category, input_type, body_area, target_freq)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                input_type = EXCLUDED.input_type,
                body_area = EXCLUDED.body_area,
                target_freq = EXCLUDED.target_freq
            """,
            (code, name, category, input_type, body_area, target_freq),
        )


def init_db():
    """Create tables, run migrations, and seed exercise data.

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
        seed_exercises(cur)
        cur.close()
    finally:
        conn.close()
