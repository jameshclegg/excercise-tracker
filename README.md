# Exercise Tracker

A Flask web app for tracking daily exercises, deployed on Render with a Neon (Postgres) database.

## Files

| File | Description |
|------|-------------|
| `app.py` | Main Flask web application — routes, database logic, exercise seeding |
| `entry.py` | CLI data entry tool for quick offline exercise logging |
| `data.txt` | Locally-entered exercise data (from `entry.py`) |
| `exercises.txt` | Master list of 38 exercise codes with categories |
| `templates/` | HTML templates (login, desktop index, mobile view) |
| `generate_hash.py` | One-time script to generate a password hash |
| `set_password.ps1` | Script to update password hash across app `.env` files |
| `pyproject.toml` | Python project config and dependencies |
| `render.yaml` | Render deployment configuration |
| `uv.lock` | Dependency lock file (uv) |

## Exercise Codes

Exercises are categorised as **strength**, **isometric**, **skill**, **fitness**, or **flexibility**. Each category determines the input type:

- **Strength** — reps + sets
- **Isometric** — time (sec) + sets
- **Skill** — time (sec) + sets
- **Fitness** — varies (distance for runs, time+sets for skipping, none for HIIT/climbing)
- **Flexibility** — no numbers

See `exercises.txt` for the full list of codes.

## Local Development

```bash
uv sync
cp .env.example .env  # add DATABASE_URL and TIMELINE_PASSWORD (hash)
uv run flask --app app run --port 5052
```

## Deployment

Deployed to [Render](https://render.com) using `render.yaml`. Requires `DATABASE_URL` and `TIMELINE_PASSWORD` environment variables.
