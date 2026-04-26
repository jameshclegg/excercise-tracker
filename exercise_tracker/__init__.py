"""Exercise Tracker — Flask application package."""

from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app():
    """Create and configure the Flask application.

    Sets up the database, registers blueprints for all route groups,
    and attaches security headers to every response.
    """
    from .config import SECRET_KEY
    from .db import close_db, init_db

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.secret_key = SECRET_KEY

    # Create tables and run migrations on startup
    init_db()

    # Ensure DB connections are returned to the pool after each request,
    # even if the view function raises an exception
    app.teardown_appcontext(close_db)

    # Security headers applied to every response
    @app.after_request
    def set_security_headers(response):
        # Prevent browsers from MIME-sniffing the content-type
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Block embedding in iframes (clickjacking protection)
        response.headers["X-Frame-Options"] = "DENY"
        # Enable browser XSS filtering
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Only send full referrer to same origin; cross-origin gets origin only
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # HSTS: force HTTPS for 1 year (skip in debug to allow local HTTP)
        if not app.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    # Register route blueprints — each group handles a distinct concern:
    # auth: login/logout, main: web UI pages, api: JSON endpoints, telegram: bot webhook
    from .routes.auth_routes import bp as auth_bp
    from .routes.main_routes import bp as main_bp
    from .routes.api_routes import bp as api_bp
    from .routes.telegram_routes import bp as telegram_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(telegram_bp)

    return app
