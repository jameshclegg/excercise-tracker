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

# Code aliases for bulk entry parsing
CODE_ALIASES = {
    "hiit": "HH", "climbing": "CC", "climb": "CC",
    "dq": "SQ", "gm": "GM", "gr": "GR",
}
SUFFIX_ALIASES = {
    "b*": "Bs", "r*": "Rs", "s*": "SP", "w*": "WW", "e'": "Ex",
    "t*": "PP", "v*": "VG", "g*": "GF",
}


def get_valid_codes():
    """Get set of valid exercise codes from DB."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM exercises")
    codes = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return codes


def normalize_code(raw_code, valid_codes):
    """Normalize an exercise code to its canonical form."""
    code = raw_code.strip()
    lower = code.lower()
    if lower in CODE_ALIASES:
        return CODE_ALIASES[lower]
    if lower in SUFFIX_ALIASES:
        return SUFFIX_ALIASES[lower]
    for valid in valid_codes:
        if valid.lower() == lower:
            return valid
    return code


def smart_split(codes_str):
    """Split exercise entries by comma, keeping 'v a,b,c' together."""
    result = []
    remaining = codes_str
    while remaining:
        remaining = remaining.strip()
        if not remaining:
            break
        v_match = re.match(r'^(v\s+[a-e](?:\s*,\s*[a-e])*)', remaining, re.IGNORECASE)
        if v_match:
            result.append(v_match.group(1))
            remaining = remaining[v_match.end():].lstrip()
            if remaining.startswith(','):
                remaining = remaining[1:]
            continue
        comma_idx = remaining.find(',')
        if comma_idx == -1:
            result.append(remaining)
            break
        else:
            result.append(remaining[:comma_idx])
            remaining = remaining[comma_idx + 1:]
    return result


def parse_bulk_entry(raw_entry, valid_codes):
    """
    Parse a single exercise entry like 'p -13 5 4', 'a 1', 'vb', 'hiit'.
    Returns list of (code, sets_str, weight, notes) tuples.
    """
    raw = raw_entry.strip()
    if not raw:
        return []

    # Handle 'v a,b,c' patterns
    v_match = re.match(r'^v\s+([a-e](?:\s*,\s*[a-e])*)\s*$', raw, re.IGNORECASE)
    if v_match:
        letters = re.findall(r'[a-eA-E]', v_match.group(1))
        return [("V" + l.upper(), None, None, None) for l in letters]

    # Handle bare 'v' or 'v 1'
    if re.match(r'^v\s*$', raw, re.IGNORECASE) or re.match(r'^v\s+1\s*$', raw, re.IGNORECASE):
        return [("VA", None, None, None), ("VB", None, None, None),
                ("VC", None, None, None), ("VD", None, None, None),
                ("VE", None, None, None)]

    parts = raw.split()
    code = normalize_code(parts[0], valid_codes)
    rest = parts[1:]

    if not rest:
        return [(code, None, None, None)]

    sets_str = None
    weight = None
    notes = None
    i = 0

    # Weight (negative number)
    if i < len(rest) and rest[i].startswith('-'):
        try:
            weight = abs(float(rest[i]))
            i += 1
        except ValueError:
            pass

    # Fraction like '2/3'
    if i < len(rest) and '/' in rest[i] and not rest[i].startswith('-'):
        notes = f"{rest[i]} of routine"
        return [(code, None, weight, notes)]

    # Sets/reps value
    if i < len(rest):
        val = rest[i]
        if '+' in val:
            sets_str = val
            i += 1
        else:
            try:
                num = float(val)
                i += 1
                if i < len(rest):
                    try:
                        set_count = int(rest[i])
                        i += 1
                        if num == int(num):
                            sets_str = "+".join([str(int(num))] * set_count)
                        else:
                            sets_str = "+".join([str(num)] * set_count)
                    except ValueError:
                        sets_str = str(int(num)) if num == int(num) else str(num)
                else:
                    sets_str = str(int(num)) if num == int(num) else str(num)
            except ValueError:
                pass

    # Fraction after numbers
    if i < len(rest) and '/' in rest[i]:
        notes = f"{rest[i]} of routine"

    return [(code, sets_str, weight, notes)]


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
            m = re.match(r"^(\S+)\s*=\s*(.+?)\s*\[(\w+)\](?:\s*\{(\w+)\})?\s*$", line)
            if m:
                code, name, category = m.group(1), m.group(2).strip(), m.group(3)
                body_area = m.group(4)  # None if not specified
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

    selected_date = request.args.get("date", date.today().isoformat())

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

    stats_data = _compute_stats_data()

    return render_template(
        "index.html",
        exercises=exercises,
        entries=entries,
        selected_date=selected_date,
        next_date=next_date,
        recent_dates=recent_dates,
        input_types=INPUT_TYPES,
        **stats_data,
    )


@app.route("/m")
@require_login
def mobile():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM exercises ORDER BY code")
    exercises = cur.fetchall()

    selected_date = request.args.get("date", date.today().isoformat())

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
    bulk_text = request.form.get("bulk", "").strip()
    entry_date = request.form.get("date", date.today().isoformat())

    if bulk_text:
        valid_codes = get_valid_codes()
        raw_entries = smart_split(bulk_text)
        conn = get_db()
        cur = conn.cursor()
        errors = []
        count = 0
        for raw in raw_entries:
            parsed = parse_bulk_entry(raw, valid_codes)
            for code, sets_str, weight, notes in parsed:
                if code not in valid_codes:
                    errors.append(f"Unknown code: {code}")
                    continue
                cur.execute(
                    "INSERT INTO entries (date, exercise_code, sets, weight, notes) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (entry_date, code, sets_str, weight, notes),
                )
                count += 1
        cur.close()
        conn.close()
        if errors:
            flash(f"Added {count} entries. Errors: {'; '.join(errors)}")
        elif count > 0:
            flash(f"Added {count} entries")

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


def _compute_stats_data():
    """Compute all stats data. Returns a dict of template variables."""
    from collections import defaultdict

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT code, name, category, input_type FROM exercises ORDER BY category, code")
    exercises = cur.fetchall()
    exercise_map = {e["code"]: e for e in exercises}

    cur.execute("""
        SELECT e.date, e.exercise_code, e.sets, e.weight,
               ex.name, ex.category, ex.input_type
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        ORDER BY e.date
    """)
    all_entries = cur.fetchall()

    cur.execute("""
        SELECT date, COUNT(*) as count
        FROM entries
        WHERE date >= CURRENT_DATE - INTERVAL '12 months'
        GROUP BY date ORDER BY date
    """)
    daily_counts = {r["date"].isoformat(): r["count"] for r in cur.fetchall()}

    cur.execute("""
        SELECT e.date, ex.code, ex.name
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        WHERE e.date >= CURRENT_DATE - INTERVAL '12 months'
        ORDER BY e.date, ex.name
    """)
    daily_exercises = {}
    for r in cur.fetchall():
        d = r["date"].isoformat()
        if d not in daily_exercises:
            daily_exercises[d] = []
        label = f"{r['code']} ({r['name']})"
        if label not in daily_exercises[d]:
            daily_exercises[d].append(label)

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

    cur.execute("""
        SELECT TO_CHAR(date, 'YYYY-MM') as month, COUNT(*) as count
        FROM entries GROUP BY month ORDER BY month
    """)
    monthly_volume = [{"month": r["month"], "count": r["count"]} for r in cur.fetchall()]

    cur.execute("""
        SELECT ex.category, COUNT(*) as count
        FROM entries e JOIN exercises ex ON e.exercise_code = ex.code
        GROUP BY ex.category
    """)
    category_dist = {r["category"]: r["count"] for r in cur.fetchall()}

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

    timeline_data = {}
    for entry in all_entries:
        code = entry["exercise_code"]
        if code not in timeline_data:
            timeline_data[code] = []
        timeline_data[code].append(entry["date"].isoformat())

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

    progress_data = {k: v for k, v in progress_data.items() if len(v["dates"]) >= 5}

    today = date.today()
    exercise_stats = []
    for r in exercise_stats_raw:
        code = r["exercise_code"]
        dates_list = sorted(set(timeline_data.get(code, [])))
        date_objs = [date.fromisoformat(d) for d in dates_list]

        current_streak = 0
        if date_objs:
            check = date_objs[-1]
            idx = len(date_objs) - 1
            while idx >= 0 and date_objs[idx] == check:
                current_streak += 1
                check -= timedelta(days=1)
                idx -= 1

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

    exercise_stats.sort(key=lambda x: x["days_since"], reverse=True)

    quarterly_entries = defaultdict(list)
    for entry in all_entries:
        m = entry["date"].month
        q = (m - 1) // 3 + 1
        q_key = f"{entry['date'].year}-Q{q}"
        quarterly_entries[q_key].append(entry)

    quarter_labels = {1: "Jan–Mar", 2: "Apr–Jun", 3: "Jul–Sep", 4: "Oct–Dec"}
    quarterly_narratives = []
    prev_quarter_codes = set()
    for q_key in sorted(quarterly_entries.keys()):
        entries = quarterly_entries[q_key]
        year, q_num = q_key.split("-Q")
        q_label = f"{quarter_labels[int(q_num)]} {year}"

        code_counts = defaultdict(int)
        active_days = set()
        for e in entries:
            code_counts[e["exercise_code"]] += 1
            active_days.add(e["date"])

        top = sorted(code_counts.items(), key=lambda x: x[1], reverse=True)
        top_names = [f"{exercise_map[c]['name']} ({n}x)" for c, n in top[:7] if c in exercise_map]

        cat_counts = defaultdict(int)
        for e in entries:
            cat_counts[e["category"]] += 1
        dominant_cat = max(cat_counts.items(), key=lambda x: x[1])[0] if cat_counts else "none"

        current_codes = set(code_counts.keys())
        new_exercises = current_codes - prev_quarter_codes if prev_quarter_codes else set()
        dropped = prev_quarter_codes - current_codes if prev_quarter_codes else set()

        progress_notes = []
        q_month_prefixes = []
        q_int = int(q_num)
        for m in range((q_int - 1) * 3 + 1, q_int * 3 + 1):
            q_month_prefixes.append(f"{year}-{m:02d}")

        for code in list(code_counts.keys()):
            if code not in progress_data:
                continue
            pd = progress_data[code]
            q_values = []
            for d, v in zip(pd["dates"], pd["values"]):
                if any(d.startswith(p) for p in q_month_prefixes):
                    q_values.append(v)
            if len(q_values) >= 3:
                first_val = q_values[0]
                last_val = q_values[-1]
                if last_val > first_val * 1.1:
                    unit = "km" if pd["input_type"] == "distance" else "reps" if pd["input_type"] == "reps_sets" else "sec"
                    name = exercise_map[code]["name"] if code in exercise_map else code
                    progress_notes.append(
                        f"{name} improved from {first_val:.0f} to {last_val:.0f} {unit}"
                    )
                elif last_val < first_val * 0.9:
                    unit = "km" if pd["input_type"] == "distance" else "reps" if pd["input_type"] == "reps_sets" else "sec"
                    name = exercise_map[code]["name"] if code in exercise_map else code
                    progress_notes.append(
                        f"{name} decreased from {first_val:.0f} to {last_val:.0f} {unit}"
                    )

        parts = []
        parts.append(f"You trained on <strong>{len(active_days)}</strong> days with "
                     f"<strong>{len(entries)}</strong> total exercise entries.")
        parts.append(f"Most focus was on <strong>{dominant_cat}</strong>. "
                     f"Top exercises: {', '.join(top_names)}.")

        if new_exercises:
            new_names = [exercise_map[c]["name"] for c in new_exercises if c in exercise_map]
            if new_names:
                parts.append(f"🆕 Started: {', '.join(sorted(new_names)[:6])}.")
        if dropped:
            drop_names = [exercise_map[c]["name"] for c in dropped if c in exercise_map]
            if drop_names and len(drop_names) <= 10:
                parts.append(f"⏸️ Paused: {', '.join(sorted(drop_names)[:6])}.")

        if progress_notes:
            parts.append("📈 " + ". ".join(progress_notes[:4]) + ".")

        quarterly_narratives.append({
            "quarter": q_key,
            "label": q_label,
            "narrative": " ".join(parts),
            "active_days": len(active_days),
            "total_entries": len(entries),
        })

        prev_quarter_codes = current_codes

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

    best_map = {}
    for pb in personal_bests:
        code = pb["code"]
        if code not in best_map or pb["value"] > best_map[code]["value"]:
            best_map[code] = pb
    personal_bests = sorted(best_map.values(), key=lambda x: x["value"], reverse=True)

    return {
        "exercises_json": json.dumps([dict(e) for e in exercises]),
        "daily_counts_json": json.dumps(daily_counts),
        "daily_exercises_json": json.dumps(daily_exercises),
        "timeline_json": json.dumps(timeline_data),
        "progress_json": json.dumps(progress_data),
        "category_dist_json": json.dumps(category_dist),
        "weekly_volume_json": json.dumps(weekly_volume),
        "monthly_volume_json": json.dumps(monthly_volume),
        "exercise_stats": exercise_stats,
        "personal_bests": personal_bests,
        "exercise_map": exercise_map,
        "monthly_narratives": quarterly_narratives,
    }


@app.route("/stats")
@require_login
def stats():
    return render_template("stats.html", **_compute_stats_data())


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5052)
