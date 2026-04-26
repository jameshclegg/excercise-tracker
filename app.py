"""Exercise Tracker - application entry point."""

import os

from exercise_tracker import create_app

app = create_app()

if __name__ == "__main__":
    # Port 5052 avoids conflicts with other local Flask apps;
    # debug mode is opt-in via FLASK_DEBUG env var
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() == "true", port=5052)
