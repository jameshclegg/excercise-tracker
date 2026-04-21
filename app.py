import json
import os
import re
from datetime import date, datetime, timedelta

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ["DATABASE_URL"]
PASSWORD_HASH = os.environ.get("TIMELINE_PASSWORD", "")

EXERCISES_FILE = os.path.join(os.path.dirname(__file__), "exercises.txt")

# Input type determines which fields are shown in the UI
INPUT_TYPES = {
    "reps_sets": {"sets": "Sets (e.g. 15+12+10)", "weight": "Weight (kg)"},
    "time_sets": {"sets": "Sets (sec, e.g. 45+45+45)", "weight": "Weight (kg)"},
    "distance": {"sets": "Distance (km)"},
    "none": {},
}

# Map category to default input_type, with per-code overrides
CATEGORY_DEFAULT_INPUT = {
    "strength": "reps_sets",
    "isometric": "time_sets",
    "skill": "time_sets",
    "flexibility": "none",
    "fitness": "none",
}

CODE_INPUT_OVERRIDES = {
    "J": "distance",
    "E": "time_sets",
}


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            input_type TEXT NOT NULL
        )
    """)
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
    seed_exercises(cur)
    cur.close()
    conn.close()


def parse_exercises_file():
    exercises = []
    with open(EXERCISES_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(\S+)\s*=\s*(.+?)\s*\[(\w+)\]\s*$", line)
            if m:
                code, name, category = m.group(1), m.group(2).strip(), m.group(3)
                input_type = CODE_INPUT_OVERRIDES.get(
                    code, CATEGORY_DEFAULT_INPUT.get(category, "none")
                )
                exercises.append((code, name, category, input_type))
    return exercises


def seed_exercises(cur):
    exercises = parse_exercises_file()
    for code, name, category, input_type in exercises:
        cur.execute(
            """
            INSERT INTO exercises (code, name, category, input_type)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                input_type = EXCLUDED.input_type
            """,
            (code, name, category, input_type),
        )


def require_login(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if check_password_hash(PASSWORD_HASH, request.form.get("password", "")):
            session["logged_in"] = True
            return redirect(url_for("index"))
        flash("Wrong password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@require_login
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM exercises ORDER BY code")
    exercises = cur.fetchall()
    exercise_map = {e["code"]: e for e in exercises}

    selected_date = request.args.get("date", "2025-01-03")

    cur.execute(
        """
        SELECT e.*, ex.name, ex.category, ex.input_type
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        WHERE e.date = %s
        ORDER BY e.created_at
        """,
        (selected_date,),
    )
    entries = cur.fetchall()

    # Recent dates with entries
    cur.execute(
        """
        SELECT DISTINCT date FROM entries
        ORDER BY date DESC LIMIT 14
        """
    )
    recent_dates = [r["date"].isoformat() for r in cur.fetchall()]

    next_date = (date.fromisoformat(selected_date) + timedelta(days=1)).isoformat()

    cur.close()
    conn.close()
    return render_template(
        "index.html",
        exercises=exercises,
        exercise_map=exercise_map,
        entries=entries,
        selected_date=selected_date,
        next_date=next_date,
        recent_dates=recent_dates,
        input_types=INPUT_TYPES,
    )


@app.route("/m")
@require_login
def mobile():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM exercises ORDER BY code")
    exercises = cur.fetchall()

    selected_date = request.args.get("date", "2025-01-03")

    cur.execute(
        """
        SELECT e.*, ex.name, ex.category, ex.input_type
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        WHERE e.date = %s
        ORDER BY e.created_at
        """,
        (selected_date,),
    )
    entries = cur.fetchall()

    next_date = (date.fromisoformat(selected_date) + timedelta(days=1)).isoformat()

    cur.close()
    conn.close()
    return render_template(
        "mobile.html",
        exercises=exercises,
        entries=entries,
        selected_date=selected_date,
        next_date=next_date,
        input_types=INPUT_TYPES,
    )


@app.route("/add", methods=["POST"])
@require_login
def add_entry():
    exercise_code = request.form.get("exercise_code", "").strip()
    entry_date = request.form.get("date", date.today().isoformat())
    sets_val = request.form.get("sets", "").strip() or None
    weight = request.form.get("weight")
    notes = request.form.get("notes", "").strip() or None

    weight = float(weight) if weight else None

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO entries (date, exercise_code, sets, weight, notes)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (entry_date, exercise_code, sets_val, weight, notes),
    )
    cur.close()
    conn.close()

    redirect_to = request.form.get("redirect", "/")
    next_date = (date.fromisoformat(entry_date) + timedelta(days=1)).isoformat()
    return redirect(f"{redirect_to}?date={next_date}")


@app.route("/delete/<int:entry_id>", methods=["POST"])
@require_login
def delete_entry(entry_id):
    entry_date = request.form.get("date", date.today().isoformat())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM entries WHERE id = %s", (entry_id,))
    cur.close()
    conn.close()

    redirect_to = request.form.get("redirect", "/")
    return redirect(f"{redirect_to}?date={entry_date}")


@app.route("/api/exercises")
@require_login
def api_exercises():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM exercises ORDER BY code")
    exercises = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(exercises)


@app.route("/stats")
@require_login
def stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # All exercises
    cur.execute("SELECT code, name, category, input_type FROM exercises ORDER BY category, code")
    exercises = cur.fetchall()
    exercise_map = {e["code"]: e for e in exercises}

    # All entries with exercise info
    cur.execute("""
        SELECT e.date, e.exercise_code, e.sets, e.weight,
               ex.name, ex.category, ex.input_type
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        ORDER BY e.date
    """)
    all_entries = cur.fetchall()

    # Daily counts for heatmap (last 12 months)
    cur.execute("""
        SELECT date, COUNT(*) as count
        FROM entries
        WHERE date >= CURRENT_DATE - INTERVAL '12 months'
        GROUP BY date ORDER BY date
    """)
    daily_counts = {r["date"].isoformat(): r["count"] for r in cur.fetchall()}

    # Weekly volume by category
    cur.execute("""
        SELECT TO_CHAR(e.date, 'IYYY-IW') as year_week,
               MIN(e.date) as week_start,
               ex.category,
               COUNT(*) as count
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        GROUP BY year_week, ex.category
        ORDER BY year_week
    """)
    weekly_raw = cur.fetchall()
    weekly_volume = {}
    for r in weekly_raw:
        wk = r["week_start"].isoformat()
        if wk not in weekly_volume:
            weekly_volume[wk] = {}
        weekly_volume[wk][r["category"]] = r["count"]

    # Monthly volume
    cur.execute("""
        SELECT TO_CHAR(date, 'YYYY-MM') as month, COUNT(*) as count
        FROM entries GROUP BY month ORDER BY month
    """)
    monthly_volume = [{"month": r["month"], "count": r["count"]} for r in cur.fetchall()]

    # Category distribution
    cur.execute("""
        SELECT ex.category, COUNT(*) as count
        FROM entries e JOIN exercises ex ON e.exercise_code = ex.code
        GROUP BY ex.category
    """)
    category_dist = {r["category"]: r["count"] for r in cur.fetchall()}

    # Per-exercise stats
    cur.execute("""
        SELECT e.exercise_code, ex.name, ex.category, ex.input_type,
               COUNT(*) as total_count,
               MAX(e.date) as last_done,
               MIN(e.date) as first_done
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        GROUP BY e.exercise_code, ex.name, ex.category, ex.input_type
        ORDER BY MAX(e.date) DESC
    """)
    exercise_stats_raw = cur.fetchall()

    cur.close()
    conn.close()

    # Build timeline data: for each exercise, list of dates
    timeline_data = {}
    for entry in all_entries:
        code = entry["exercise_code"]
        if code not in timeline_data:
            timeline_data[code] = []
        timeline_data[code].append(entry["date"].isoformat())

    # Build progress data: for exercises with sets data, track values over time
    progress_data = {}
    for entry in all_entries:
        code = entry["exercise_code"]
        sets_str = entry["sets"]
        if not sets_str:
            continue
        input_type = entry["input_type"]
        try:
            if input_type == "distance":
                value = float(sets_str)
            elif input_type in ("reps_sets", "time_sets"):
                parts = sets_str.split("+")
                value = sum(float(p) for p in parts)
            else:
                continue
        except (ValueError, TypeError):
            continue

        if code not in progress_data:
            progress_data[code] = {"dates": [], "values": [], "input_type": input_type}
        progress_data[code]["dates"].append(entry["date"].isoformat())
        progress_data[code]["values"].append(value)

    # Filter progress data to exercises with 5+ data points
    progress_data = {k: v for k, v in progress_data.items() if len(v["dates"]) >= 5}

    # Compute streaks and consistency scores
    today = date.today()
    exercise_stats = []
    for r in exercise_stats_raw:
        code = r["exercise_code"]
        dates_list = sorted(set(timeline_data.get(code, [])))
        date_objs = [date.fromisoformat(d) for d in dates_list]

        # Current streak
        current_streak = 0
        if date_objs:
            check = date_objs[-1]
            idx = len(date_objs) - 1
            while idx >= 0 and date_objs[idx] == check:
                current_streak += 1
                check -= timedelta(days=1)
                idx -= 1

        # Longest streak
        longest_streak = 0
        if date_objs:
            streak = 1
            for i in range(1, len(date_objs)):
                if (date_objs[i] - date_objs[i-1]).days == 1:
                    streak += 1
                else:
                    longest_streak = max(longest_streak, streak)
                    streak = 1
            longest_streak = max(longest_streak, streak)

        days_since = (today - r["last_done"]).days

        exercise_stats.append({
            "code": code,
            "name": r["name"],
            "category": r["category"],
            "input_type": r["input_type"],
            "total_count": r["total_count"],
            "last_done": r["last_done"].isoformat(),
            "days_since": days_since,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
        })

    # Sort by days_since (most neglected first)
    exercise_stats.sort(key=lambda x: x["days_since"], reverse=True)

    # Personal bests
    personal_bests = []
    for entry in all_entries:
        code = entry["exercise_code"]
        sets_str = entry["sets"]
        if not sets_str:
            continue
        input_type = entry["input_type"]
        try:
            if input_type == "reps_sets":
                parts = sets_str.split("+")
                value = sum(float(p) for p in parts)
                label = f"{int(value)} total reps"
            elif input_type == "time_sets":
                parts = sets_str.split("+")
                value = max(float(p) for p in parts)
                label = f"{value}s hold"
            elif input_type == "distance":
                value = float(sets_str)
                label = f"{value} km"
            else:
                continue
        except (ValueError, TypeError):
            continue

        personal_bests.append({
            "code": code,
            "name": entry["name"],
            "category": entry["category"],
            "value": value,
            "label": label,
            "date": entry["date"].isoformat(),
        })

    # Keep only the best per exercise
    best_map = {}
    for pb in personal_bests:
        code = pb["code"]
        if code not in best_map or pb["value"] > best_map[code]["value"]:
            best_map[code] = pb
    personal_bests = sorted(best_map.values(), key=lambda x: x["value"], reverse=True)

    return render_template(
        "stats.html",
        exercises_json=json.dumps([dict(e) for e in exercises]),
        daily_counts_json=json.dumps(daily_counts),
        timeline_json=json.dumps(timeline_data),
        progress_json=json.dumps(progress_data),
        category_dist_json=json.dumps(category_dist),
        weekly_volume_json=json.dumps(weekly_volume),
        monthly_volume_json=json.dumps(monthly_volume),
        exercise_stats=exercise_stats,
        personal_bests=personal_bests,
        exercise_map=exercise_map,
    )


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5052)
