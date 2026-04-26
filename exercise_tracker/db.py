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


def parse_exercises_file():
    exercises = []
    with open(EXERCISES_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
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
        # Migrate: add body_area column if missing
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'exercises' AND column_name = 'body_area'
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE exercises ADD COLUMN body_area TEXT")
        # Migrate: drop old schema if it has num1/num2/num3 columns
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
        # Migrate: rename mixed-case codes to uppercase
        code_renames = [("Bs", "BS"), ("Rs", "RS"), ("Ex", "EX"), ("Gx", "GX"), ("Gy", "GY")]
        for old, new in code_renames:
            cur.execute("SELECT 1 FROM exercises WHERE code = %s", (old,))
            if cur.fetchone():
                cur.execute("UPDATE entries SET exercise_code = %s WHERE exercise_code = %s", (new, old))
                cur.execute("UPDATE exercise_notes SET exercise_code = %s WHERE exercise_code = %s", (new, old))
                cur.execute("DELETE FROM exercises WHERE code = %s", (old,))
        # Migrate: add target_freq column if missing
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'exercises' AND column_name = 'target_freq'
        """)
        if not cur.fetchone():
            cur.execute("ALTER TABLE exercises ADD COLUMN target_freq NUMERIC(4,2) DEFAULT 1")
        # Migrate: change target_freq from INTEGER to NUMERIC if needed
        cur.execute("""
            SELECT data_type FROM information_schema.columns
            WHERE table_name = 'exercises' AND column_name = 'target_freq'
        """)
        col_type = cur.fetchone()
        if col_type and col_type[0] == 'integer':
            cur.execute("ALTER TABLE exercises ALTER COLUMN target_freq TYPE NUMERIC(4,2)")
        # Migrate: merge SS into SP and delete SS
        cur.execute("SELECT 1 FROM exercises WHERE code = 'SS'")
        if cur.fetchone():
            cur.execute("UPDATE entries SET exercise_code = 'SP' WHERE exercise_code = 'SS'")
            cur.execute("UPDATE exercise_notes SET exercise_code = 'SP' WHERE exercise_code = 'SS'")
            cur.execute("DELETE FROM exercises WHERE code = 'SS'")
        seed_exercises(cur)
        cur.close()
    finally:
        conn.close()
