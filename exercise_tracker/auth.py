"""Authentication helpers."""

from functools import wraps

from flask import redirect, request, session, url_for, flash
from werkzeug.security import check_password_hash

from .config import PASSWORD_HASH


def require_login(f):
    """Decorator that redirects unauthenticated users to the login page.

    If PASSWORD_HASH is empty (not configured), authentication is bypassed
    entirely — this allows running without a password in development or
    single-user deployments where the app is behind another auth layer.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if PASSWORD_HASH and not session.get("logged_in"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated
