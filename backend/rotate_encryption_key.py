"""Move the database from the current ENCRYPTION_KEY to a new one.

    # 1. stop the backend — a server still running on the old key would write
    #    new rows under it, and read rotated rows as unreadable
    # 2. check: decrypts every value with the current key, changes nothing
    python rotate_encryption_key.py
    # 3. rotate (the new key comes from the environment, not the command line,
    #    so it stays out of shell history)
    NEW_ENCRYPTION_KEY=<32 characters> python rotate_encryption_key.py --apply
    # 4. put the new key in .env as ENCRYPTION_KEY, then start the backend

The current key is the ENCRYPTION_KEY the backend reads (backend/.env). Back up
the database first: the run is a single transaction and rolls back on any
failure, but a backup is the only remedy for losing the new key afterwards.
"""

import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import psycopg  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.key_rotation import RotationError, rotate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true",
                        help="write the re-encrypted values (default: check only)")
    args = parser.parse_args()

    settings = get_settings()
    new_key = os.getenv("NEW_ENCRYPTION_KEY", "")
    if args.apply and not new_key:
        parser.error("set NEW_ENCRYPTION_KEY to the new 32-character key")
    if not args.apply and not new_key:
        # A dry run only needs to prove the current key opens everything.
        new_key = os.urandom(16).hex()

    try:
        with psycopg.connect(settings.DATABASE_URL) as conn:
            report = rotate(conn, settings.ENCRYPTION_KEY, new_key, apply=args.apply)
    except RotationError as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1

    for column, tally in report.columns.items():
        if tally.rotated or tally.unencrypted:
            note = f", {tally.unencrypted} not encrypted (left as is)" if tally.unencrypted else ""
            print(f"  {column:48} {tally.rotated:6} values{note}")
    if args.apply:
        print(f"\nRe-encrypted {report.rotated} values. Set ENCRYPTION_KEY to the new key in "
              ".env now, then start the backend.")
    else:
        print(f"\nCheck passed: all {report.rotated} encrypted values open with the current key. "
              "Nothing was changed. Run again with --apply and NEW_ENCRYPTION_KEY to rotate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
