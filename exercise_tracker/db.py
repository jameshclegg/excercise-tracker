"""Database connection and initialization."""

import re

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import (
    CATEGORY_DEFAULT_INPUT,
    CODE_INPUT_OVERRIDES,
    DATABASE_URL,
    EXERCISES_FILE,
)


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def parse_exercises_file():
    exercises = []
    with open(EXERCISES_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(\S+)\s*=\s*(.+?)\s*\[(\w+)\](?:\s*\{(\w+)\})?\s*$", line)
            if m:
                code, name, category = m.group(1), m.group(2).strip(), m.group(3)
                body_area = m.group(4)
                input_type = CODE_INPUT_OVERRIDES.get(
                    code, CATEGORY_DEFAULT_INPUT.get(category, "none")
                )
                exercises.append((code, name, category, input_type, body_area))
    return exercises


def seed_exercises(cur):
    exercises = parse_exercises_file()
    for code, name, category, input_type, body_area in exercises:
        cur.execute(
            """
            INSERT INTO exercises (code, name, category, input_type, body_area)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                input_type = EXCLUDED.input_type,
                body_area = EXCLUDED.body_area
            """,
            (code, name, category, input_type, body_area),
        )


def init_db():
    conn = get_db()
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
    seed_exercises(cur)
    cur.close()
    conn.close()
