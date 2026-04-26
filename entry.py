"""
CLI data entry tool for exercise tracking.

Usage: python entry.py [datafile]

Commands during entry:
  <code>    Add an exercise code to the current date
  nn        Move to next day (enter again to skip a day)
  bb        Go back one day to review/correct
  del <N>   Delete entry number N from current day
  list      Show entries for current day
  show      Show all recorded data
  save      Save and quit
  q/quit    Quit (auto-saves)
  help      Show this help
"""

import os
import sys
import atexit
from datetime import date, timedelta
from collections import OrderedDict
from pathlib import Path

START_DATE = date(2025, 1, 3)
DEFAULT_FILE = "data/data.txt"
LOCK_SUFFIX = ".lock"


def acquire_lock(filepath):
    """Create a lock file to prevent concurrent instances."""
    lockfile = Path(str(filepath) + LOCK_SUFFIX)
    if lockfile.exists():
        print(f"ERROR: Another instance appears to be running (lock file exists: {lockfile})")
        print("If no other instance is running, delete the lock file and try again.")
        sys.exit(1)
    lockfile.write_text(str(os.getpid()))
    atexit.register(release_lock, lockfile)


def release_lock(lockfile):
    """Remove the lock file."""
    try:
        Path(lockfile).unlink()
    except OSError:
        pass


def load_data(filepath):
    """Load existing data from file. Returns OrderedDict of date -> list of codes."""
    data = OrderedDict()
    path = Path(filepath)
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            if ": " in line:
                date_str, codes_str = line.split(": ", 1)
                codes = [c.strip() for c in codes_str.split(",") if c.strip()]
                data[date_str] = codes
            else:
                data[line.rstrip(":")] = []
    except FileNotFoundError:
        pass
    return data


def save_data(filepath, data):
    """Save data to file."""
    path = Path(filepath)
    lines = []
    for date_str, codes in data.items():
        if codes:
            lines.append(f"{date_str}: {', '.join(codes)}")
    path.write_text("\n".join(lines) + "\n" if lines else "")


def date_to_str(d):
    return d.isoformat()


def find_resume_date(data):
    """Find the next date to resume entry from."""
    if not data:
        return START_DATE
    last_date_str = list(data.keys())[-1]
    last_date = date.fromisoformat(last_date_str)
    return last_date + timedelta(days=1)


def print_day(date_str, data):
    """Print entries for a given date."""
    codes = data.get(date_str, [])
    if codes:
        print(f"  Entries for {date_str}:")
        for i, code in enumerate(codes, 1):
            print(f"    {i}. {code}")
    else:
        print(f"  No entries for {date_str}")


def print_help():
    print("""
Commands:
  <code>    Add an exercise code to the current date
  nn        Move to next day (enter again to skip days)
  bb        Go back one day to review/correct
  del <N>   Delete entry number N from current day
  list      Show entries for current day
  show      Show all recorded data
  save      Save and quit
  q/quit    Quit (auto-saves)
  help      Show this help
""")


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__)
        sys.exit(0)

    filepath = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    acquire_lock(filepath)
    data = load_data(filepath)

    current_date = find_resume_date(data)

    print(f"Exercise entry tool — data file: {filepath}")
    if data:
        print(f"Loaded {len(data)} days of existing data.")
    print(f"Type 'help' for commands.\n")
    print(f"--- {date_to_str(current_date)} ({current_date.strftime('%A')}) ---")
    print_day(date_to_str(current_date), data)

    while True:
        try:
            raw = input(f"[{date_to_str(current_date)}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        cmd = raw.lower()

        if cmd in ("q", "quit", "save"):
            break

        elif cmd == "help":
            print_help()

        elif cmd == "nn":
            current_date += timedelta(days=1)
            ds = date_to_str(current_date)
            print(f"\n--- {ds} ({current_date.strftime('%A')}) ---")
            print_day(ds, data)

        elif cmd == "bb":
            current_date -= timedelta(days=1)
            if current_date < START_DATE:
                current_date = START_DATE
                print("  (Can't go before start date)")
            ds = date_to_str(current_date)
            print(f"\n--- {ds} ({current_date.strftime('%A')}) ---")
            print_day(ds, data)

        elif cmd == "list":
            print_day(date_to_str(current_date), data)

        elif cmd == "show":
            if not data:
                print("  No data recorded yet.")
            else:
                print()
                for d, codes in data.items():
                    day_name = date.fromisoformat(d).strftime("%a")
                    print(f"  {d} ({day_name}): {', '.join(codes)}")
                print()

        elif cmd.startswith("del ") or cmd.startswith("del\t"):
            parts = raw.split(None, 1)
            if len(parts) < 2 or not parts[1].isdigit():
                print("  Usage: del <number>")
                continue
            idx = int(parts[1])
            ds = date_to_str(current_date)
            codes = data.get(ds, [])
            if idx < 1 or idx > len(codes):
                print(f"  Invalid entry number. Current entries: 1-{len(codes)}" if codes else "  No entries to delete.")
                continue
            removed = codes.pop(idx - 1)
            if not codes:
                del data[ds]
            print(f"  Deleted: {removed}")
            print_day(ds, data)
            save_data(filepath, data)

        else:
            # Treat as exercise code
            ds = date_to_str(current_date)
            if ds not in data:
                data[ds] = []
            data[ds].append(raw)
            print(f"  Added: {raw}")
            save_data(filepath, data)

    # Final save on exit (redundant but safe)
    save_data(filepath, data)
    print(f"Saved to {filepath}.")


if __name__ == "__main__":
    main()
