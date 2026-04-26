"""Export exercise entries from Neon DB to data.txt format."""

import os
import sys
from collections import OrderedDict
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def export_data(output_file="data/data_export.txt"):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT date, exercise_code, sets, weight, notes
        FROM entries
        ORDER BY date, id
    """)
    rows = cur.fetchall()

    days = OrderedDict()
    for row_date, code, sets_str, weight, notes in rows:
        date_str = row_date.isoformat()
        if date_str not in days:
            days[date_str] = []

        parts = [code]
        if weight is not None:
            w = float(weight)
            parts.append(f"-{w:g}")
        if sets_str is not None:
            parts.append(sets_str)
        if notes and "of routine" in notes:
            frac = notes.replace(" of routine", "")
            parts.append(frac)

        days[date_str].append(" ".join(parts))

    output_path = Path(output_file)
    output_path.write_text(
        "".join(f"{d}: {', '.join(e)}\n" for d, e in days.items())
    )

    print(f"Exported {len(rows)} entries across {len(days)} days to {output_file}")

    # Export exercise notes
    cur.execute("""
        SELECT en.exercise_code, e.name, en.notes
        FROM exercise_notes en
        JOIN exercises e ON en.exercise_code = e.code
        ORDER BY en.exercise_code
    """)
    note_rows = cur.fetchall()

    if note_rows:
        notes_path = Path(output_file.replace("data_export", "notes_export").replace("data.txt", "notes.txt"))
        if str(notes_path) == output_file:
            notes_path = Path("data/notes_export.txt")
        lines = []
        for code, name, notes_text in note_rows:
            lines.append(f"[{code}] {name}\n")
            for line in notes_text.split("\n"):
                lines.append(f"  {line}\n")
            lines.append("\n")
        notes_path.write_text("".join(lines))
        print(f"Exported {len(note_rows)} exercise notes to {notes_path}")
    else:
        print("No exercise notes to export")

    # Export injury notes
    cur.execute("SELECT notes FROM injury_notes WHERE id = 1")
    injury_row = cur.fetchone()
    cur.close()
    conn.close()

    injury_path = Path("data/injury_notes.txt")
    if injury_row and injury_row[0].strip():
        text = injury_row[0]
        if not text.endswith("\n"):
            text += "\n"
        injury_path.write_text(text)
        print(f"Exported injury notes to {injury_path}")
    else:
        print("No injury notes to export")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "data/data_export.txt"
    export_data(output)
