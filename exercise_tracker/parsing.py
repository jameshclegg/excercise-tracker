"""Parsing logic for exercise entries."""

import re

from .config import CODE_ALIASES, SUFFIX_ALIASES
from .db import get_db


def get_valid_codes():
    """Return the set of all valid exercise codes from the database."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM exercises")
    codes = {r[0] for r in cur.fetchall()}
    return codes


def normalize_code(raw_code, valid_codes):
    """Normalize an exercise code to its canonical form."""
    code = raw_code.strip()
    lower = code.lower()
    if lower in CODE_ALIASES:
        return CODE_ALIASES[lower]
    if lower in SUFFIX_ALIASES:
        return SUFFIX_ALIASES[lower]
    for valid in valid_codes:
        if valid.lower() == lower:
            return valid
    return code


def smart_split(codes_str):
    """Split exercise entries by comma, keeping 'v a,b,c' together.

    The 'v' (flexibility) shorthand uses commas between variant letters,
    which would normally be split. This function detects that pattern and
    preserves 'v a,b,c' as a single token.
    """
    tokens = codes_str.split(",")
    result = []
    i = 0
    while i < len(tokens):
        token = tokens[i].strip()
        if not token:
            i += 1
            continue
        parts = token.split()
        if parts and parts[0].lower() == "v" and len(parts) >= 2:
            # Collect v variants until we hit a non-single-letter token
            v_parts = [token]
            while i + 1 < len(tokens):
                next_t = tokens[i + 1].strip()
                if re.match(r"^[a-zA-Z]$", next_t):
                    v_parts.append(next_t)
                    i += 1
                else:
                    break
            result.append(",".join(v_parts))
        else:
            result.append(token)
        i += 1
    return result


def parse_bulk_entry(raw_entry, valid_codes):
    """Parse a bulk entry string into a list of (code, sets_str, weight, notes) tuples.

    Supports several shorthand forms:
    - 'v' alone → expand to all flexibility codes VA–VE
    - 'v a,b,c' → expand to VA, VB, VC
    - 'v N' (N<=5) → first N flexibility codes
    - 'CODE -W R C' → exercise at Weight, Reps × Count (e.g. 'p -13 15 3')
    - 'CODE 15+12+10' → explicit sets in plus notation
    - 'CODE 2/3' → fraction stored as notes ('2/3 of routine')
    """
    items = smart_split(raw_entry)
    results = []
    for item in items:
        item = item.strip()
        if not item:
            continue

        # Handle "v a,b,c" or bare "v" or "v 1" expansions
        # 'v' is a shorthand for flexibility exercises VA through VE
        parts = item.split()
        lower0 = parts[0].lower()
        if lower0 == "v":
            if len(parts) == 1:
                # Bare 'v' → all flexibility codes VA-VE
                for suffix in ["A", "B", "C", "D", "E"]:
                    code = f"V{suffix}"
                    if code in valid_codes:
                        results.append((code, None, None, None))
                continue
            second = parts[1]
            if "," in item[len(parts[0]):]:
                # v a,b,c format
                letters_str = item[len(parts[0]):].strip()
                letters = [l.strip().upper() for l in letters_str.split(",") if l.strip()]
                for letter in letters:
                    code = f"V{letter}"
                    if code in valid_codes:
                        results.append((code, None, None, None))
                continue
            if re.match(r"^\d+$", second):
                num = int(second)
                # If num <= 5, treat as "first N flexibility variants" (VA..VE)
                # If num > 5, fall through to standard parsing (e.g. reps count)
                if num <= 5:
                    for suffix in ["A", "B", "C", "D", "E"][:num]:
                        code = f"V{suffix}"
                        if code in valid_codes:
                            results.append((code, None, None, None))
                    continue

        # Standard parsing: CODE [-WEIGHT] [SETS] [FRAC]
        code_raw = parts[0]
        code = normalize_code(code_raw, valid_codes)
        weight = None
        sets_str = None
        notes = None
        rest = parts[1:]

        idx = 0
        # Check for weight: negative number prefix convention (e.g. '-13' = 13kg)
        if idx < len(rest) and re.match(r"^-\d+(\.\d+)?$", rest[idx]):
            weight = float(rest[idx][1:])
            idx += 1

        # Collect sets data: plus notation ('15+12+10'), individual numbers,
        # or 'REPS COUNT' shorthand ('15 3' → '15+15+15')
        set_parts = []
        while idx < len(rest):
            token = rest[idx]
            if re.match(r"^\d+(\+\d+)*$", token):
                if "+" in token:
                    set_parts.append(token)
                else:
                    set_parts.append(token)
                idx += 1
            elif re.match(r"^\d+/\d+$", token):
                # Fraction like '2/3' → stored as notes (partial routine)
                notes = f"{token} of routine"
                idx += 1
            else:
                break

        # Reject leftover unparsed tokens (e.g. 'Ti 6 5 4 rr')
        if idx < len(rest):
            raise ValueError(
                f"Unexpected token(s) after '{code_raw}': {' '.join(rest[idx:])}"
            )

        # Reject 3+ bare numbers with no plus notation (e.g. 'Ti 6 5 4')
        if (len(set_parts) > 2
                and all(s.isdigit() for s in set_parts)
                and not any("+" in s for s in set_parts)):
            raise ValueError(
                f"Too many numbers for '{code_raw}': {' '.join(set_parts)} "
                f"(expected at most REPS COUNT)"
            )

        # Convert collected set_parts into the canonical plus notation:
        # - Single plus-notation token kept as-is ('15+12+10')
        # - Two bare numbers become reps × count ('15 3' → '15+15+15')
        # - Otherwise join with '+' ('15+12')
        if set_parts:
            if len(set_parts) == 1 and "+" in set_parts[0]:
                sets_str = set_parts[0]
            elif len(set_parts) >= 2 and all(s.isdigit() for s in set_parts):
                reps = set_parts[0]
                count = int(set_parts[1])
                sets_str = "+".join([reps] * count)
            else:
                sets_str = "+".join(set_parts)

        results.append((code, sets_str, weight, notes))

    return results
