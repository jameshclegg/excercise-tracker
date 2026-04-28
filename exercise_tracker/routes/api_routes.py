"""API routes — exercises, notes, injury notes, recent history."""

from collections import OrderedDict

from flask import Blueprint, jsonify, request, Response
import json
from psycopg2.extras import RealDictCursor

from ..auth import require_login
from ..db import get_db
from ..parsing import get_valid_codes

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/exercises")
@require_login
def exercises():
    """Return all exercises as JSON, ordered by code."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM exercises ORDER BY code")
    exercises = cur.fetchall()
    return jsonify(exercises)


@bp.route("/notes", methods=["GET"])
@require_login
def get_notes():
    """Return all exercise notes as JSON."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT exercise_code, notes, updated_at FROM exercise_notes ORDER BY exercise_code")
    notes = cur.fetchall()
    return jsonify(notes)


@bp.route("/notes", methods=["POST"])
@require_login
def save_note():
    """Create or update an exercise note. Deletes the note if text is blank.

    Expects JSON: {"exercise_code": "P", "notes": "Focus on form"}
    """
    data = request.get_json()
    code = data.get("exercise_code", "").strip()
    notes_text = data.get("notes", "").strip()
    if not code:
        return jsonify({"error": "exercise_code required"}), 400
    valid_codes = get_valid_codes()
    if code not in valid_codes:
        return jsonify({"error": "unknown exercise code"}), 404

    conn = get_db()
    cur = conn.cursor()
    # Upsert when there's text; delete the row entirely when blank
    # to keep the table clean (no empty-note rows)
    if notes_text:
        cur.execute("""
            INSERT INTO exercise_notes (exercise_code, notes, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (exercise_code) DO UPDATE SET
                notes = EXCLUDED.notes,
                updated_at = NOW()
        """, (code, notes_text))
    else:
        cur.execute("DELETE FROM exercise_notes WHERE exercise_code = %s", (code,))
    return jsonify({"ok": True})


@bp.route("/injury-notes", methods=["GET"])
@require_login
def get_injury_notes():
    """Return the global injury notes (singleton row, id=1)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT notes FROM injury_notes WHERE id = 1")
    row = cur.fetchone()
    return jsonify({"notes": row[0] if row else ""})


@bp.route("/injury-notes", methods=["POST"])
@require_login
def save_injury_notes():
    """Upsert the global injury notes (singleton row, id=1)."""
    data = request.get_json()
    notes_text = data.get("notes", "").strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO injury_notes (id, notes, updated_at)
        VALUES (1, %s, NOW())
        ON CONFLICT (id) DO UPDATE SET
            notes = EXCLUDED.notes,
            updated_at = NOW()
    """, (notes_text,))
    return jsonify({"ok": True})


@bp.route("/recent/<code>")
@require_login
def recent(code):
    """Return history for a single exercise, grouped by date.

    By default, fetches the last 10 entries and groups them into the
    3 most recent dates. If ?full=1 is passed, fetches ALL entries
    with no date limit. Response includes exercise name, per-date
    entry details, and any saved exercise notes.
    """
    valid_codes = get_valid_codes()
    if code not in valid_codes:
        return jsonify({"error": "unknown exercise code"}), 404
    full = request.args.get("full") == "1"
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # In full mode, fetch all entries; otherwise limit to 10
    query = """
        SELECT e.date, e.sets, e.weight, e.notes, ex.name, ex.input_type, ex.target_freq
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        WHERE e.exercise_code = %s
        ORDER BY e.date DESC, e.id DESC
    """
    if not full:
        query += " LIMIT 10"
    cur.execute(query, (code,))
    rows = cur.fetchall()
    cur.execute("SELECT notes FROM exercise_notes WHERE exercise_code = %s", (code,))
    notes_row = cur.fetchone()
    # Group by date — in default mode, keep only the 3 most recent
    # dates to avoid overwhelming the popup with old data
    by_date = OrderedDict()
    for r in rows:
        d = r["date"].isoformat()
        if d not in by_date:
            if not full and len(by_date) >= 3:
                break
            by_date[d] = []
        by_date[d].append({
            "sets": r["sets"], "weight": float(r["weight"]) if r["weight"] else None,
            "notes": r["notes"], "input_type": r["input_type"]
        })
    freq = float(rows[0]["target_freq"]) if rows and rows[0]["target_freq"] else 1
    freq_label = f"{freq:g}x/wk"
    # Use json.dumps with sort_keys=False to preserve date ordering
    # (Flask's jsonify sorts keys alphabetically, reversing our DESC order)
    return Response(
        json.dumps({
            "name": rows[0]["name"] if rows else code,
            "dates": by_date,
            "exercise_notes": notes_row["notes"] if notes_row else None,
            "freq_label": freq_label
        }, sort_keys=False),
        mimetype="application/json"
    )
