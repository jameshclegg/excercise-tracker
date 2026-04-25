"""Plan computation: to-do and slipping exercise lists."""

from datetime import date, timedelta

from psycopg2.extras import RealDictCursor

from .db import get_db


def compute_plan_data():
    """Compute to-do and slipping exercise lists.

    To-do: exercises done in last 7 days but not in last 2 days,
           with most recent entry details.
    Slipping: exercises done in last 30 days but not in last 7 days.
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    today = date.today()

    # To-do: done in last 7 days but not last 2 days
    cur.execute(
        """
        SELECT DISTINCT e.exercise_code AS code, ex.name
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        WHERE e.date >= %s AND e.date < %s
          AND e.exercise_code NOT IN (
              SELECT DISTINCT exercise_code FROM entries WHERE date >= %s
          )
        ORDER BY ex.name
        """,
        (
            (today - timedelta(days=7)).isoformat(),
            (today - timedelta(days=1)).isoformat(),
            (today - timedelta(days=2)).isoformat(),
        ),
    )
    todo_codes = cur.fetchall()

    # For each to-do exercise, get most recent entry details
    todo_items = []
    for row in todo_codes:
        cur.execute(
            """
            SELECT e.date, e.sets, e.weight
            FROM entries e
            WHERE e.exercise_code = %s
            ORDER BY e.date DESC, e.id DESC
            LIMIT 1
            """,
            (row["code"],),
        )
        last = cur.fetchone()
        parts = [row["code"]]
        if last and last["sets"]:
            parts.append(last["sets"])
        if last and last["weight"]:
            parts.append(f"@ {last['weight']}kg")
        todo_items.append({
            "code": row["code"],
            "name": row["name"],
            "last_entry": " ".join(parts),
            "days_ago": (today - last["date"]).days if last else None,
        })

    # Sort by most neglected first (highest days_ago)
    todo_items.sort(key=lambda x: x["days_ago"] or 999, reverse=True)

    # Slipping: done in last 30 days but not last 7 days
    cur.execute(
        """
        SELECT DISTINCT e.exercise_code AS code, ex.name
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        WHERE e.date >= %s AND e.date < %s
          AND e.exercise_code NOT IN (
              SELECT DISTINCT exercise_code FROM entries WHERE date >= %s
          )
        ORDER BY ex.name
        """,
        (
            (today - timedelta(days=30)).isoformat(),
            (today - timedelta(days=7)).isoformat(),
            (today - timedelta(days=7)).isoformat(),
        ),
    )
    slipping_items = cur.fetchall()

    cur.close()
    conn.close()
    return {"todo_items": todo_items, "slipping_items": slipping_items}
