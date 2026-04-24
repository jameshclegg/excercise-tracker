"""Authentication helpers."""

from functools import wraps

from flask import redirect, request, session, url_for, flash
from werkzeug.security import check_password_hash

from .config import PASSWORD_HASH


def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if PASSWORD_HASH and not session.get("logged_in"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated
