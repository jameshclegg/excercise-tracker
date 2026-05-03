"""Auth routes — login/logout."""

import time
from collections import defaultdict, deque

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from ..config import PASSWORD_HASH

bp = Blueprint("auth", __name__)

# In-memory per-IP login attempt tracking. Per-worker only (Render runs
# multiple gunicorn workers), but still meaningfully slows brute-force.
_RATE_LIMIT_WINDOW = 300  # 5 minutes
_RATE_LIMIT_MAX = 10      # max failed attempts per window
_login_attempts: dict[str, deque] = defaultdict(deque)


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = _login_attempts[ip]
    while attempts and now - attempts[0] > _RATE_LIMIT_WINDOW:
        attempts.popleft()
    return len(attempts) >= _RATE_LIMIT_MAX


def _record_failed_attempt(ip: str) -> None:
    _login_attempts[ip].append(time.time())


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        if _is_rate_limited(ip):
            flash("Too many failed attempts. Try again in a few minutes.")
            return render_template("login.html"), 429
        if check_password_hash(PASSWORD_HASH, request.form.get("password", "")):
            session["logged_in"] = True
            _login_attempts.pop(ip, None)
            return redirect(url_for("main.index"))
        _record_failed_attempt(ip)
        flash("Wrong password")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("auth.login"))
