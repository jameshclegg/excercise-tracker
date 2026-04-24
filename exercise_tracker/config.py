"""Application constants and configuration."""

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "")
PASSWORD_HASH = os.environ.get("TIMELINE_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
EXERCISES_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "exercises.txt")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Input type determines which fields are shown in the UI
INPUT_TYPES = {
    "reps_sets": {"sets": "Sets (e.g. 15+12+10)", "weight": "Weight (kg)"},
    "time_sets": {"sets": "Sets (sec, e.g. 45+45+45)", "weight": "Weight (kg)"},
    "distance": {"sets": "Distance (km)"},
    "none": {},
}

# Map category to default input_type, with per-code overrides
CATEGORY_DEFAULT_INPUT = {
    "strength": "reps_sets",
    "isometric": "time_sets",
    "skill": "time_sets",
    "flexibility": "none",
    "fitness": "none",
}

CODE_INPUT_OVERRIDES = {
    "J": "distance",
    "E": "time_sets",
}

# Code aliases for bulk entry parsing
CODE_ALIASES = {
    "hiit": "HH", "climbing": "CC", "climb": "CC",
    "dq": "SQ", "gm": "GM", "gr": "GR",
}
SUFFIX_ALIASES = {
    "b*": "BS", "r*": "RS", "s*": "SP", "w*": "WW", "e'": "EX",
    "t*": "PP", "v*": "VG", "g*": "GF",
}
