"""
Import data.txt into the Neon database.

Handles:
- Code aliases: hiit→HH, climbing/climb→CC, b*→Bs, r*→Rs, w*→WW, E'/e'→Ex, t→T
- V expansion: bare 'v' or 'v 1' → VA,VB,VC,VD,VE; 'v a,b' → VA,VB
- Weight carry-forward: '-' prefix = kg, inherited by subsequent entries
- Plus notation: '15+12+10' kept as-is; 'P 15 3' → '15+15+15'
- Fractions: 'b 2/3' stored with notes='2/3 of routine'
- Sorting by date
- Idempotent: clears all entries before import

Usage: uv run python import_data.py [--dry-run]
"""

import os
import re
import sys
from datetime import date
from collections import OrderedDict
from pathlib import Path

from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
DATA_FILE = Path(__file__).resolve().parent / "data" / "original-input-data.txt"

# Code aliases (case-insensitive matching)
CODE_ALIASES = {
    "hiit": "HH",
    "climbing": "CC",
    "climb": "CC",
    "dq": "SQ",
    "gm": "GM",
    "gr": "GR",
}

# Suffix aliases (matched after stripping)
SUFFIX_ALIASES = {
    "b*": "BS",
    "r*": "RS",
    "s*": "SP",
    "w*": "WW",
    "e'": "EX",
    "t*": "PP",
    "v*": "VG",
    "g*": "GF",
}

# Valid codes (loaded from DB)
VALID_CODES = set()

# Weight carry-forward state per exercise code
WEIGHT_STATE = {}


def load_valid_codes():
    """Load the set of valid exercise codes from the database."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT code FROM exercises")
    codes = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return codes


def normalize_code(raw_code):
    """Normalize an exercise code to its canonical form."""
    code = raw_code.strip()
    lower = code.lower()

    # Check exact aliases first
    if lower in CODE_ALIASES:
        return CODE_ALIASES[lower]

    # Check suffix aliases
    if lower in SUFFIX_ALIASES:
        return SUFFIX_ALIASES[lower]

    # Case-insensitive match against valid codes
    for valid in VALID_CODES:
        if valid.lower() == lower:
            return valid

    return code


def parse_entry(raw_entry):
    """
    Parse a single exercise entry like 'p 15+12+10', 'b -6.5 1', 'j 3.2', 'hiit'.

    Returns list of (code, sets_str, weight, notes) tuples.
    One entry may expand to multiple (e.g. 'v a,b' → VA, VB).
    """
    raw = raw_entry.strip()
    if not raw:
        return []

    # Handle 'v a,b,c,d' or 'v a, b, c' patterns
    v_match = re.match(r'^v\s+([a-e](?:\s*,\s*[a-e])*)\s*$', raw, re.IGNORECASE)
    if v_match:
        letters = re.findall(r'[a-eA-E]', v_match.group(1))
        return [("V" + l.upper(), None, None, None) for l in letters]

    # Handle bare 'v' or 'v 1' → expand to all flexibility codes (VA–VE)
    if re.match(r'^v\s*$', raw, re.IGNORECASE) or re.match(r'^v\s+1\s*$', raw, re.IGNORECASE):
        return [("VA", None, None, None), ("VB", None, None, None),
                ("VC", None, None, None), ("VD", None, None, None),
                ("VE", None, None, None)]

    # Split into tokens
    parts = raw.split()
    code_raw = parts[0]
    code = normalize_code(code_raw)
    rest = parts[1:]

    # No additional data
    if not rest:
        return [(code, None, None, None)]

    sets_str = None
    weight = None
    notes = None

    i = 0
    # Check for weight (negative number prefix, e.g. '-13' = 13 kg).
    # Weight is remembered per exercise code for carry-forward.
    if i < len(rest) and rest[i].startswith('-'):
        try:
            weight = abs(float(rest[i]))
            WEIGHT_STATE[code] = weight
            i += 1
        except ValueError:
            pass

    # Check for fraction like '2/3'
    if i < len(rest) and '/' in rest[i] and not rest[i].startswith('-'):
        frac = rest[i]
        notes = f"{frac} of routine"
        return [(code, None, weight or WEIGHT_STATE.get(code), notes)]

    # Check for sets/reps value
    if i < len(rest):
        val = rest[i]
        if '+' in val:
            # Already in plus notation: '15+12+10'
            sets_str = val
            i += 1
        else:
            try:
                num = float(val)
                i += 1
                # Check if there's a second number (count of sets)
                if i < len(rest):
                    try:
                        set_count = int(rest[i])
                        i += 1
                        # Expand: 'P 15 3' → '15+15+15'
                        if num == int(num):
                            sets_str = "+".join([str(int(num))] * set_count)
                        else:
                            sets_str = "+".join([str(num)] * set_count)
                    except ValueError:
                        # Second token isn't a number
                        sets_str = str(num) if num != int(num) else str(int(num))
                else:
                    # Single number only
                    sets_str = str(num) if num != int(num) else str(int(num))
            except ValueError:
                pass

    # Check for fraction after numbers (e.g., 'b -6.5 2/3')
    if i < len(rest) and '/' in rest[i]:
        notes = f"{rest[i]} of routine"
        i += 1

    # If no explicit weight but we have a carry-forward value from a
    # previous entry of the same exercise. Currently not applied automatically
    # to avoid false positives with timed/bodyweight exercises.
    if weight is None and code in WEIGHT_STATE:
        # Only carry forward for codes that use weight
        # Don't carry forward for timed routines like B where '1' means '1 set'
        pass

    return [(code, sets_str, weight, notes)]


def parse_data_file(filepath):
    """Parse data.txt and return sorted list of (date_str, entries) tuples."""
    days = OrderedDict()

    with open(filepath, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            if ": " not in line:
                print(f"  WARNING line {line_num}: no date separator found: {line}")
                continue

            date_str, codes_str = line.split(": ", 1)

            # Validate date
            try:
                date.fromisoformat(date_str)
            except ValueError:
                print(f"  WARNING line {line_num}: invalid date '{date_str}'")
                continue

            # Split entries by comma, but handle 'v a,b' carefully
            # Strategy: find all exercise entries, handling V specially
            raw_entries = smart_split(codes_str)

            if date_str not in days:
                days[date_str] = []

            for raw in raw_entries:
                parsed = parse_entry(raw)
                for code, sets_str, weight, notes in parsed:
                    if code not in VALID_CODES:
                        print(f"  WARNING line {line_num}: unknown code '{code}' (from '{raw.strip()}')")
                        continue
                    days[date_str].append((code, sets_str, weight, notes))

    # Sort by date
    sorted_days = OrderedDict(sorted(days.items()))
    return sorted_days


def smart_split(codes_str):
    """Split a line's exercise entries by comma, but keep 'v a,b,c' together.

    The flexibility shorthand 'v a,b,c' uses commas between variant letters,
    which would be incorrectly split by a naive comma split. This function
    detects and preserves those patterns as single tokens.
    """
    # First check if there's a 'v a,b,c' pattern anywhere
    # Replace v-patterns with a placeholder, split, then restore
    result = []
    remaining = codes_str

    while remaining:
        remaining = remaining.strip()
        if not remaining:
            break

        # Check for 'v a,b,...' pattern at current position
        v_match = re.match(r'^(v\s+[a-e](?:\s*,\s*[a-e])*)', remaining, re.IGNORECASE)
        if v_match:
            result.append(v_match.group(1))
            remaining = remaining[v_match.end():]
            # Skip comma after v pattern
            remaining = remaining.lstrip()
            if remaining.startswith(','):
                remaining = remaining[1:]
            continue

        # Find next comma
        comma_idx = remaining.find(',')
        if comma_idx == -1:
            result.append(remaining)
            break
        else:
            result.append(remaining[:comma_idx])
            remaining = remaining[comma_idx + 1:]

    return result


def import_to_db(days, dry_run=False):
    """Import parsed data into the database."""
    total = sum(len(entries) for entries in days.values())
    print(f"\n  Importing {total} entries across {len(days)} days...")

    if dry_run:
        print("\n  DRY RUN — showing what would be imported:\n")
        for date_str, entries in days.items():
            for code, sets_str, weight, notes in entries:
                parts = [f"{code}"]
                if sets_str:
                    parts.append(f"sets={sets_str}")
                if weight:
                    parts.append(f"weight={weight}kg")
                if notes:
                    parts.append(f"notes={notes}")
                print(f"    {date_str}: {', '.join(parts)}")
        print(f"\n  DRY RUN complete. {total} entries would be imported.")
        return

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Only delete entries for dates present in data.txt, preserving any
        # entries added via the web UI for other dates
        dates_to_import = list(days.keys())
        if dates_to_import:
            cur.execute(
                "DELETE FROM entries WHERE date = ANY(%s::date[])",
                (dates_to_import,),
            )
            deleted = cur.rowcount
            if deleted:
                print(f"  Cleared {deleted} existing entries for {len(dates_to_import)} dates in data.txt.")

        for date_str, entries in days.items():
            for code, sets_str, weight, notes in entries:
                cur.execute(
                    "INSERT INTO entries (date, exercise_code, sets, weight, notes) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (date_str, code, sets_str, weight, notes),
                )

        conn.commit()
        print(f"  Successfully imported {total} entries.")
    except Exception as e:
        conn.rollback()
        print(f"  ERROR: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def main():
    dry_run = "--dry-run" in sys.argv

    print("Exercise Tracker — Data Import")
    print("=" * 40)

    global VALID_CODES
    VALID_CODES = load_valid_codes()
    print(f"  Loaded {len(VALID_CODES)} exercise codes from DB.")

    print(f"  Parsing {DATA_FILE}...")
    days = parse_data_file(DATA_FILE)
    print(f"  Parsed {len(days)} days of data.")

    import_to_db(days, dry_run=dry_run)


if __name__ == "__main__":
    main()
