"""Stats computation for exercise tracking."""

import json
from collections import defaultdict
from datetime import date

from psycopg2.extras import RealDictCursor

from .db import get_db


def compute_stats_data():
    """Compute all stats data. Returns a dict of template variables."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT code, name, category, input_type, body_area FROM exercises ORDER BY category, code")
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
        days_since = (today - r["last_done"]).days
        exercise_stats.append({
            "code": code,
            "name": r["name"],
            "category": r["category"],
            "input_type": r["input_type"],
            "total_count": r["total_count"],
            "last_done": r["last_done"].isoformat(),
            "days_since": days_since,
        })

    exercise_stats.sort(key=lambda x: x["days_since"], reverse=False)

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
