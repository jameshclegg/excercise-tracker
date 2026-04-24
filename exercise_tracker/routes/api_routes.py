"""API routes — exercises, notes, injury notes, recent history."""

from collections import OrderedDict

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from ..auth import require_login
from ..db import get_db

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/exercises")
@require_login
def exercises():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM exercises ORDER BY code")
    exercises = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(exercises)


@bp.route("/notes", methods=["GET"])
@require_login
def get_notes():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT exercise_code, notes, updated_at FROM exercise_notes ORDER BY exercise_code")
    notes = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(notes)


@bp.route("/notes", methods=["POST"])
@require_login
def save_note():
    data = request.get_json()
    code = data.get("exercise_code", "").strip()
    notes_text = data.get("notes", "").strip()
    if not code:
        return jsonify({"error": "exercise_code required"}), 400

    conn = get_db()
    cur = conn.cursor()
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
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/injury-notes", methods=["GET"])
@require_login
def get_injury_notes():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT notes FROM injury_notes WHERE id = 1")
    row = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({"notes": row[0] if row else ""})


@bp.route("/injury-notes", methods=["POST"])
@require_login
def save_injury_notes():
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
    cur.close()
    conn.close()
    return jsonify({"ok": True})


@bp.route("/recent/<code>")
@require_login
def recent(code):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT e.date, e.sets, e.weight, e.notes, ex.name, ex.input_type
        FROM entries e
        JOIN exercises ex ON e.exercise_code = ex.code
        WHERE e.exercise_code = %s
        ORDER BY e.date DESC, e.id DESC
        LIMIT 10
    """, (code,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    # Group by date (most recent 3 dates)
    by_date = OrderedDict()
    for r in rows:
        d = r["date"].isoformat()
        if d not in by_date:
            if len(by_date) >= 3:
                break
            by_date[d] = []
        by_date[d].append({
            "sets": r["sets"], "weight": float(r["weight"]) if r["weight"] else None,
            "notes": r["notes"], "input_type": r["input_type"]
        })
    return jsonify({"name": rows[0]["name"] if rows else code, "dates": by_date})
