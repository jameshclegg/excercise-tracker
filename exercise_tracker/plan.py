"""Plan computation: to-do, slipping, and dormant exercise lists."""

from datetime import date, timedelta

from psycopg2.extras import RealDictCursor

from .db import get_db

# Exercises not done for 5+ weeks are considered dormant (abandoned)
# and excluded from to-do/slipping lists to reduce noise
DORMANT_DAYS = 35


def compute_plan_data():
    """Compute to-do and slipping exercise lists based on target frequency.

    To-do: days_since_last >= 7/freq AND days_since_last < 14
    Slipping: days_since_last >= 14 AND days_since_last < DORMANT_DAYS
    Dormant (>= DORMANT_DAYS): not shown
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

        if days_since >= DORMANT_DAYS:
            continue  # dormant

        # Derive the expected interval from target frequency:
        # e.g. freq=2 means twice/week → 7/2=3.5 → floor to 3 days
        # Floor ensures exercises appear in todo promptly rather than waiting
        # an extra day when the interval isn't a whole number.
        interval = int(7.0 / float(freq))
        freq_label = f"{float(freq):g}x/wk"

        if days_since >= 14:
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

    return {"todo_items": todo_items, "slipping_items": slipping_items}
