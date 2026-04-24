"""Exercise Tracker - application entry point."""

from exercise_tracker import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5052)
