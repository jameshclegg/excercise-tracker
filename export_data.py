"""Export exercise entries from Neon DB to data.txt format."""

import os
import sys
from collections import OrderedDict

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

    with open(output_file, "w") as f:
        for date_str, entries in days.items():
            f.write(f"{date_str}: {', '.join(entries)}\n")

    print(f"Exported {len(rows)} entries across {len(days)} days to {output_file}")

    # Export exercise notes
    cur.execute("""
        SELECT en.exercise_code, e.name, en.notes
        FROM exercise_notes en
        JOIN exercises e ON en.exercise_code = e.code
        ORDER BY en.exercise_code
    """)
    note_rows = cur.fetchall()
    cur.close()
    conn.close()

    if note_rows:
        notes_file = output_file.replace("data_export", "notes_export").replace("data.txt", "notes.txt")
        if notes_file == output_file:
            notes_file = "data/notes_export.txt"
        with open(notes_file, "w") as f:
            for code, name, notes_text in note_rows:
                f.write(f"[{code}] {name}\n")
                for line in notes_text.split("\n"):
                    f.write(f"  {line}\n")
                f.write("\n")
        print(f"Exported {len(note_rows)} exercise notes to {notes_file}")
    else:
        print("No exercise notes to export")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "data/data_export.txt"
    export_data(output)
