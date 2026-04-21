"""Export exercise entries from Neon DB to data.txt format."""

import os
import sys
from collections import OrderedDict

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def export_data(output_file="data_export.txt"):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT date, exercise_code, sets, weight, notes
        FROM entries
        ORDER BY date, id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

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


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "data_export.txt"
    export_data(output)
