"""Exercise Tracker - application entry point."""

import os

from exercise_tracker import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() == "true", port=5052)
