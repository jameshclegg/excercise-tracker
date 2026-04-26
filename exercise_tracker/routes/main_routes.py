"""Main page routes — index, mobile, add, delete, stats."""

from collections import OrderedDict
from datetime import date, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request
from psycopg2.extras import RealDictCursor

from ..auth import require_login
from ..config import INPUT_TYPES
from ..db import get_db
from ..parsing import get_valid_codes, parse_bulk_entry, smart_split
from ..plan import compute_plan_data
from ..stats import compute_stats_data

bp = Blueprint("main", __name__)


@bp.route("/")
@require_login
def index():
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

    # Recent dates with entries
    cur.execute(
        """
        SELECT DISTINCT date FROM entries
        ORDER BY date DESC LIMIT 14
        """
    )
    recent_dates = [r["date"].isoformat() for r in cur.fetchall()]

    next_date = (date.fromisoformat(selected_date) + timedelta(days=1)).isoformat()

    stats_data = compute_stats_data()
    plan_data = compute_plan_data()

    return render_template(
        "index.html",
        exercises=exercises,
        entries=entries,
        selected_date=selected_date,
        next_date=next_date,
        recent_dates=recent_dates,
        input_types=INPUT_TYPES,
        **stats_data,
        **plan_data,
    )


@bp.route("/m")
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

    return render_template(
        "mobile.html",
        exercises=exercises,
        entries=entries,
        selected_date=selected_date,
        next_date=next_date,
        input_types=INPUT_TYPES,
    )


@bp.route("/add", methods=["POST"])
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
        if errors:
            flash(f"Added {count} entries. Errors: {'; '.join(errors)}")
        elif count > 0:
            flash(f"Added {count} entries")

    redirect_to = request.form.get("redirect", "/")
    return redirect(f"{redirect_to}?date={entry_date}")


@bp.route("/delete/<int:entry_id>", methods=["POST"])
@require_login
def delete_entry(entry_id):
    entry_date = request.form.get("date", date.today().isoformat())
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM entries WHERE id = %s", (entry_id,))

    redirect_to = request.form.get("redirect", "/")
    return redirect(f"{redirect_to}?date={entry_date}")


@bp.route("/stats")
@require_login
def stats():
    return render_template("stats.html", **compute_stats_data())
