"""Exercise Tracker — Flask application package."""

from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app():
    from .config import SECRET_KEY
    from .db import init_db

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.secret_key = SECRET_KEY

    # Initialize database
    init_db()

    # Register blueprints
    from .routes.auth_routes import bp as auth_bp
    from .routes.main_routes import bp as main_bp
    from .routes.api_routes import bp as api_bp
    from .routes.telegram_routes import bp as telegram_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(telegram_bp)

    return app
