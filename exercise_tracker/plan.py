"""Plan computation: to-do, slipping, and dormant exercise lists."""

from datetime import date, timedelta

from psycopg2.extras import RealDictCursor

from .db import get_db


def compute_plan_data():
    """Compute to-do and slipping exercise lists based on target frequency.

    Thresholds scale with each exercise's interval (7/freq):
    - To-do: days_since >= interval
    - Slipping: days_since >= 3 * interval
    - Dormant (>= 6 * interval): not shown
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    today = date.today()

    # Get all exercises with their target frequency and last done date
    cur.execute(
        """
        SELECT ex.code, ex.name, ex.target_freq,
               MAX(e.date) as last_done
        FROM exercises ex
        LEFT JOIN entries e ON ex.code = e.exercise_code
        GROUP BY ex.code, ex.name, ex.target_freq
        ORDER BY ex.name
        """
    )
    all_exercises = cur.fetchall()

    todo_items = []
    slipping_items = []

    for ex in all_exercises:
        freq = ex["target_freq"] or 1
        last_done = ex["last_done"]

        if not last_done:
            continue  # never done, skip

        days_since = (today - last_done).days

        # Derive the expected interval from target frequency:
        # e.g. freq=2 means twice/week → 7/2=3.5 → floor to 3 days
        interval = int(7.0 / float(freq))
        # Slipping and dormant thresholds scale with the interval
        slipping_threshold = interval * 3
        dormant_threshold = interval * 6
        freq_label = f"{float(freq):g}x/wk"

        if days_since >= dormant_threshold:
            continue  # dormant

        if days_since >= slipping_threshold:
            # Slipping
            slipping_items.append({
                "code": ex["code"],
                "name": ex["name"],
                "days_ago": days_since,
                "freq_label": freq_label,
            })
        elif days_since >= interval:
            # To-do: get last entry details
            cur.execute(
                """
                SELECT e.date, e.sets, e.weight
                FROM entries e
                WHERE e.exercise_code = %s
                ORDER BY e.date DESC, e.id DESC
                LIMIT 1
                """,
                (ex["code"],),
            )
            last = cur.fetchone()
            parts = [ex["code"]]
            if last and last["sets"]:
                parts.append(last["sets"])
            if last and last["weight"]:
                parts.append(f"@ {last['weight']}kg")
            todo_items.append({
                "code": ex["code"],
                "name": ex["name"],
                "last_entry": " ".join(parts),
                "days_ago": days_since,
                "freq_label": freq_label,
            })

    # Sort by most neglected first
    todo_items.sort(key=lambda x: x["days_ago"], reverse=True)
    slipping_items.sort(key=lambda x: x["days_ago"], reverse=True)

    # Fetch due reminders (reminder_date <= today, not dismissed)
    cur.execute("""
        SELECT id, reminder_date, text
        FROM reminders
        WHERE dismissed = FALSE AND reminder_date <= %s
        ORDER BY reminder_date, id
    """, (today.isoformat(),))
    due_reminders = [
        {"id": r["id"], "date": r["reminder_date"].isoformat(), "text": r["text"]}
        for r in cur.fetchall()
    ]

    return {
        "todo_items": todo_items,
        "slipping_items": slipping_items,
        "due_reminders": due_reminders,
    }
