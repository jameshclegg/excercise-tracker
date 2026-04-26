"""Telegram bot webhook route."""

import json
import os
import re
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from ..config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

WEIGHT_TRACKER_URL = os.environ.get("WEIGHT_TRACKER_URL", "")
from ..db import get_db, get_db_transaction
from ..parsing import get_valid_codes, parse_bulk_entry
from ..plan import compute_plan_data

bp = Blueprint("telegram", __name__)


def telegram_reply(chat_id, text):
    """Send a reply message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(url, data=payload,
                                headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Telegram reply error: {e}")


def parse_weight(text):
    """Check if text is a weight entry: decimal between 60.0 and 99.9 with exactly 1 decimal place."""
    m = re.match(r"^(\d{2}\.\d)$", text.strip())
    if m:
        val = float(m.group(1))
        if 60.0 <= val <= 99.9:
            return val
    return None


def _collapse_sets(sets_str):
    """Collapse repeated equal sets: '9+9+9' → '9 3', '12+10+8' stays as-is."""
    if not sets_str or "+" not in sets_str:
        return sets_str
    parts = sets_str.split("+")
    if len(set(parts)) == 1:
        return f"{parts[0]} {len(parts)}"
    return sets_str


@bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    """Handle incoming Telegram bot messages.

    Supports:
    - Bot commands: /today, /recent, /plan, /todo, /slipping, /codes, /recentw
    - Per-exercise queries: 'P /recent', 'P /notes'
    - Weight logging: a decimal like '74.5' is saved as today's weight
    - Exercise logging: parsed via parse_bulk_entry (e.g. 'p -13 5 4, a 1')
    - Test mode: append '/test' to preview without saving
    """
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"ok": False, "error": "Bot not configured"}), 500

    data = request.get_json(silent=True)
    if not data or "message" not in data:
        return jsonify({"ok": True})

    message = data["message"]
    chat_id = str(message.get("chat", {}).get("id", ""))
    text = message.get("text", "").strip()

    if not text:
        return jsonify({"ok": True})

    # Chat-ID authorization: if TELEGRAM_CHAT_ID is configured, only that
    # user's messages are processed. Others are silently ignored (no error
    # leak). If not yet configured, echo the chat ID so the user can set it.
    if TELEGRAM_CHAT_ID and chat_id != TELEGRAM_CHAT_ID:
        return jsonify({"ok": True})

    # Bootstrap: if no chat ID is configured yet, tell the user their ID
    # so they can add it as an env var to lock the bot to their account
    if not TELEGRAM_CHAT_ID:
        telegram_reply(chat_id, f"👋 Your chat ID is: {chat_id}\n"
                       "Add this as TELEGRAM_CHAT_ID in your environment variables, "
                       "then restart the app to lock the bot to your account.")
        # Still process the message

    # Handle bot commands (slash-prefixed)
    if text.startswith("/"):
        lower = text.lower().strip()
        if lower in ("/todo", "/todo@" + TELEGRAM_BOT_TOKEN.split(":")[0] if TELEGRAM_BOT_TOKEN else ""):
            plan = compute_plan_data()
            if not plan["todo_items"]:
                telegram_reply(chat_id, "✅ All caught up! Nothing to do.")
            else:
                lines = ["📋 *To-Do*\n"]
                for item in plan["todo_items"]:
                    lines.append(f"  `{item['last_entry']}` — {item['name']} ({item['days_ago']}d ago)")
                telegram_reply(chat_id, "\n".join(lines))
            return jsonify({"ok": True})

        if lower in ("/slipping", "/slipping@" + TELEGRAM_BOT_TOKEN.split(":")[0] if TELEGRAM_BOT_TOKEN else ""):
            plan = compute_plan_data()
            if not plan["slipping_items"]:
                telegram_reply(chat_id, "👍 Nothing slipping!")
            else:
                lines = ["⚠️ *Slipping*\n"]
                for item in plan["slipping_items"]:
                    lines.append(f"  `{item['code']}` — {item['name']}")
                telegram_reply(chat_id, "\n".join(lines))
            return jsonify({"ok": True})

        if lower in ("/plan",):
            plan = compute_plan_data()
            lines = []
            if plan["todo_items"]:
                lines.append("📋 *To-Do*\n")
                for item in plan["todo_items"]:
                    lines.append(f"  `{item['last_entry']}` — {item['name']} ({item['days_ago']}d ago)")
            else:
                lines.append("✅ All caught up!\n")
            lines.append("")
            if plan["slipping_items"]:
                lines.append("⚠️ *Slipping*\n")
                for item in plan["slipping_items"]:
                    lines.append(f"  `{item['code']}` — {item['name']}")
            else:
                lines.append("👍 Nothing slipping!")
            telegram_reply(chat_id, "\n".join(lines))
            return jsonify({"ok": True})

        if lower.startswith("/today"):
            today_str = date.today().isoformat()
            today = date.today()
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT e.exercise_code, e.sets, e.weight, ex.name,
                       (SELECT MAX(e2.date) FROM entries e2
                        WHERE e2.exercise_code = e.exercise_code AND e2.date < %s
                       ) as prev_date
                FROM entries e
                JOIN exercises ex ON e.exercise_code = ex.code
                WHERE e.date = %s
                ORDER BY e.exercise_code
                """,
                (today_str, today_str),
            )
            rows = cur.fetchall()
            if not rows:
                telegram_reply(chat_id, f"📅 No exercises recorded for today ({today_str}).")
            else:
                # Sort by least recently done previously — surfaces the most
                # neglected exercises first so the user sees what matters
                rows.sort(key=lambda r: r["prev_date"] or date.min)
                lines = [f"📅 Today ({today_str}):\n"]
                for r in rows:
                    parts = [r["exercise_code"]]
                    if r["sets"]:
                        parts.append(_collapse_sets(r["sets"]))
                    if r["weight"]:
                        parts.append(f"@ {r['weight']}kg")
                    parts.append(f"— {r['name']}")
                    lines.append("  " + " ".join(parts))
                telegram_reply(chat_id, "\n".join(lines))
            return jsonify({"ok": True})

        if lower.startswith("/recent") and not lower.startswith("/recentw"):
            today = date.today()
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT e.date, e.exercise_code, e.sets, e.weight, ex.name
                FROM entries e
                JOIN exercises ex ON e.exercise_code = ex.code
                WHERE e.date >= %s
                ORDER BY e.date DESC, e.created_at
                """,
                ((today - timedelta(days=7)).isoformat(),),
            )
            rows = cur.fetchall()
            if not rows:
                telegram_reply(chat_id, "📊 No exercises in the last 7 days.")
                return jsonify({"ok": True})

            # Group entries by date for a day-by-day summary
            by_date = defaultdict(list)
            for r in rows:
                by_date[r["date"]].append(r)

            lines = ["📊 Last 7 days:\n"]
            for d in sorted(by_date.keys(), reverse=True):
                days_ago = (today - d).days
                day_label = "today" if days_ago == 0 else f"{days_ago}d ago"
                codes = [r["exercise_code"] for r in by_date[d]]
                # deduplicate while preserving order
                seen = set()
                unique_codes = []
                for c in codes:
                    if c not in seen:
                        seen.add(c)
                        unique_codes.append(c)
                lines.append(f"  {day_label}: {', '.join(unique_codes)}")

            # Also group by exercise for an alternative view
            by_exercise = defaultdict(list)
            for r in rows:
                by_exercise[r["exercise_code"]].append(r)

            lines.append("\n📋 By exercise:\n")
            for code in sorted(by_exercise.keys()):
                entries = by_exercise[code]
                details = []
                for e in entries:
                    days_ago = (today - e["date"]).days
                    day_label = "today" if days_ago == 0 else f"{days_ago}d ago"
                    parts = []
                    if e["sets"]:
                        parts.append(_collapse_sets(e["sets"]))
                    if e["weight"]:
                        parts.append(f"@{e['weight']}kg")
                    detail = " ".join(parts) if parts else "✓"
                    details.append(f"{detail} ({day_label})")
                lines.append(f"  {code}: {', '.join(details)}")

            telegram_reply(chat_id, "\n".join(lines))
            return jsonify({"ok": True})

        if lower.startswith("/recentw"):
            today = date.today()
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT date, weight FROM weights
                WHERE date >= %s
                ORDER BY date DESC
                """,
                ((today - timedelta(days=7)).isoformat(),),
            )
            rows = cur.fetchall()
            if not rows:
                telegram_reply(chat_id, "⚖️ No weight entries in the last 7 days.")
            else:
                import statistics
                weights = [float(r["weight"]) for r in rows]
                mean = statistics.mean(weights)
                stdev = statistics.stdev(weights) if len(weights) > 1 else 0.0

                entries = []
                for r in rows:
                    w = float(r["weight"])
                    days_ago = (today - r["date"]).days
                    if days_ago == 0:
                        entries.append(f"{w:.1f} (today)")
                    else:
                        entries.append(f"{w:.1f}")

                lines = [
                    f"⚖️ Weight — last 7 days\n",
                    f"  {', '.join(entries)}",
                    f"  Mean: {mean:.1f} kg, SD: {stdev:.1f} kg",
                ]
                telegram_reply(chat_id, "\n".join(lines))
            return jsonify({"ok": True})

        if lower.startswith("/codes"):
            today = date.today()
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                """
                SELECT ex.code, ex.name,
                       MAX(e.date) as last_done
                FROM exercises ex
                LEFT JOIN entries e ON ex.code = e.exercise_code
                GROUP BY ex.code, ex.name
                ORDER BY MAX(e.date) DESC NULLS LAST, ex.code
                """,
            )
            rows = cur.fetchall()
            lines = ["📖 Exercise codes:\n"]
            for r in rows:
                if r["last_done"]:
                    days_ago = (today - r["last_done"]).days
                    lines.append(f"  {r['code']} — {r['name']} ({days_ago}d ago)")
                else:
                    lines.append(f"  {r['code']} — {r['name']} (never)")
            telegram_reply(chat_id, "\n".join(lines))
            return jsonify({"ok": True})

        # Default help for unknown commands
        telegram_reply(chat_id, "👋 Exercise & Weight Tracker Bot\n\n"
                       "Send a weight like: 64.4\n"
                       "Or exercises like: p -13 5 4, a 1, vb\n\n"
                       "Commands:\n"
                       "/today — what you did today\n"
                       "/recent — last 7 days by date & exercise\n"
                       "/recentw — weight last 7 days\n"
                       "/codes — all exercise codes\n"
                       "/todo — exercises due\n"
                       "/slipping — exercises slipping\n"
                       "/plan — todo + slipping\n"
                       "\n"
                       "P /recent — last 4 sessions for P\n"
                       "P /notes — notes for P")
        return jsonify({"ok": True})

    # Handle [code] /recent and [code] /notes
    lower = text.lower().strip()
    recent_match = re.match(r"^(\S+)\s+/recent$", lower)
    notes_match = re.match(r"^(\S+)\s+/notes$", lower)

    if recent_match:
        code_raw = recent_match.group(1)
        valid_codes = get_valid_codes()
        from ..parsing import normalize_code
        code = normalize_code(code_raw, valid_codes)
        if code not in valid_codes:
            telegram_reply(chat_id, f"❓ Unknown exercise code: {code_raw}")
            return jsonify({"ok": True})

        today = date.today()
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT e.date, e.sets, e.weight, ex.name
            FROM entries e
            JOIN exercises ex ON e.exercise_code = ex.code
            WHERE e.exercise_code = %s
            ORDER BY e.date DESC, e.id DESC
            LIMIT 20
            """,
            (code,),
        )
        rows = cur.fetchall()

        if not rows:
            telegram_reply(chat_id, f"No history for {code}.")
            return jsonify({"ok": True})

        # Group by date, take last 4 dates
        from collections import OrderedDict
        by_date = OrderedDict()
        for r in rows:
            d = r["date"]
            if d not in by_date:
                if len(by_date) >= 4:
                    break
                by_date[d] = []
            by_date[d].append(r)

        name = rows[0]["name"]
        lines = [f"📊 {code} — {name}\n"]
        for d, entries in by_date.items():
            days_ago = (today - d).days
            day_label = "today" if days_ago == 0 else f"{days_ago}d ago"
            for e in entries:
                parts = []
                if e["sets"]:
                    parts.append(_collapse_sets(e["sets"]))
                if e["weight"]:
                    parts.append(f"@ {e['weight']}kg")
                detail = " ".join(parts) if parts else "✓"
                lines.append(f"  {day_label}: {detail}")
        telegram_reply(chat_id, "\n".join(lines))
        return jsonify({"ok": True})

    if notes_match:
        code_raw = notes_match.group(1)
        valid_codes = get_valid_codes()
        from ..parsing import normalize_code
        code = normalize_code(code_raw, valid_codes)
        if code not in valid_codes:
            telegram_reply(chat_id, f"❓ Unknown exercise code: {code_raw}")
            return jsonify({"ok": True})

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT ex.name FROM exercises ex WHERE ex.code = %s", (code,))
        ex = cur.fetchone()
        cur.execute("SELECT notes FROM exercise_notes WHERE exercise_code = %s", (code,))
        row = cur.fetchone()

        name = ex["name"] if ex else code
        if row and row["notes"].strip():
            telegram_reply(chat_id, f"📝 {code} — {name}\n\n{row['notes']}")
        else:
            telegram_reply(chat_id, f"📝 {code} — {name}\n\nNo notes.")
        return jsonify({"ok": True})

    # Check for '/test' suffix — allows previewing what would be saved
    # without actually committing to the database
    test_mode = False
    if text.lower().endswith("/test"):
        test_mode = True
        text = text[: -len("/test")].strip()

    today_str = date.today().isoformat()
    test_label = " [TEST MODE — not saved]" if test_mode else ""

    # Try weight entry first (a bare decimal like '74.5')
    weight = parse_weight(text)
    if weight is not None:
        try:
            with get_db_transaction() as conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO weights (date, weight) VALUES (%s, %s) "
                    "ON CONFLICT (date) DO UPDATE SET weight = EXCLUDED.weight",
                    (today_str, weight),
                )
            # In test mode, rollback the transaction so nothing is persisted
                if test_mode:
                    conn.rollback()
                else:
                    conn.commit()
            telegram_reply(chat_id, f"⚖️ Understood {weight} as weight {weight} kg.\n"
                           f"Posted to weight tracker for {today_str}.{test_label}")
            # Ping the weight tracker app to wake it from cold start
            if WEIGHT_TRACKER_URL and not test_mode:
                try:
                    urllib.request.urlopen(WEIGHT_TRACKER_URL, timeout=5)
                except Exception:
                    pass  # best-effort, don't fail the response
        except Exception as e:
            telegram_reply(chat_id, f"❌ Error saving weight: {e}")
        return jsonify({"ok": True})

    # Fall through: try parsing as exercise entries (e.g. 'p -13 5 4, a 1')
    try:
        valid_codes = get_valid_codes()
        parsed = parse_bulk_entry(text, valid_codes)
        if not parsed:
            telegram_reply(chat_id, "❓ I don't understand your input.\n\n"
                           "Send a weight like: 64.4\n"
                           "Or exercises like: p -13 5 4, a 1, vb")
            return jsonify({"ok": True})

        # Validate all codes exist
        invalid = [code for code, _, _, _ in parsed if code not in valid_codes]
        if invalid:
            telegram_reply(chat_id, f"❓ Unknown exercise code(s): {', '.join(invalid)}\n\n"
                           "Send a weight like: 64.4\n"
                           "Or exercises like: p -13 5 4, a 1, vb")
            return jsonify({"ok": True})

        # Use a transaction so all entries succeed or fail together.
        # In test mode, rollback after building the summary.
        summaries = []
        with get_db_transaction() as conn:
            cur = conn.cursor()
            for code, sets_str, weight_val, notes in parsed:
                cur.execute(
                    "INSERT INTO entries (date, exercise_code, sets, weight, notes) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (today_str, code, sets_str, weight_val, notes),
                )
                parts = [code]
                if sets_str:
                    parts.append(sets_str)
                if weight_val:
                    parts.append(f"@ {weight_val}kg")
                summaries.append(" ".join(parts))

            if test_mode:
                conn.rollback()
            else:
                conn.commit()

        reply = f"🏋️ Posted {len(parsed)} exercise(s) for {today_str}:{test_label}\n"
        reply += "\n".join(f"  • {s}" for s in summaries)
        telegram_reply(chat_id, reply)
    except Exception as e:
        telegram_reply(chat_id, f"❌ Error saving exercises: {e}")

    return jsonify({"ok": True})
