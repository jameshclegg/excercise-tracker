"""Application constants and configuration."""

import os
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "")
PASSWORD_HASH = os.environ.get("TIMELINE_PASSWORD", "")

# SECRET_KEY is required for Flask sessions. If not set, generate a random one
# (sessions won't persist across restarts, but the app still works for dev use).
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    import warnings
    warnings.warn("SECRET_KEY not set — using random key (sessions won't persist across restarts)")
    SECRET_KEY = os.urandom(32).hex()
EXERCISES_FILE = Path(__file__).resolve().parent.parent / "data" / "exercises.txt"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Input type determines which fields are shown in the UI
INPUT_TYPES = {
    "reps_sets": {"sets": "Sets (e.g. 15+12+10)", "weight": "Weight (kg)"},
    "time_sets": {"sets": "Sets (sec, e.g. 45+45+45)", "weight": "Weight (kg)"},
    "distance": {"sets": "Distance (km)"},
    "minutes": {"sets": "Duration (minutes)"},
    "none": {},
}

# Map category to default input_type, with per-code overrides
CATEGORY_DEFAULT_INPUT = {
    "strength": "reps_sets",
    "isometric": "time_sets",
    "skill": "time_sets",
    "flexibility": "none",
    "fitness": "none",
    "physio": "reps_sets",
    "music": "minutes",
}

CODE_INPUT_OVERRIDES = {
    "J": "distance",
    "E": "time_sets",
    "TI": "time_sets",
}

# Code aliases: common misspellings and shorthand names → canonical codes
CODE_ALIASES = {
    "hiit": "HH", "climbing": "CC", "climb": "CC",
    "dq": "SQ", "gm": "GM", "gr": "GR",
}

# Suffix aliases: keyboard-friendly shortcuts using special chars.
# e.g. 'b*' → BS (barbell squat), 'e\'' → EX (exercise), 'v*' → VG
SUFFIX_ALIASES = {
    "b*": "BS", "r*": "RS", "s*": "SP", "w*": "WW", "e'": "EX",
    "t*": "PP", "v*": "VG", "g*": "GF",
}
