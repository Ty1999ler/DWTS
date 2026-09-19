"""Load the season's cast into the league by hand.

    python load_cast.py

You normally don't need this - a fresh database seeds the cast automatically on
first start. Use it to top up a league whose couples were deleted, or after
editing the list in cast_data.py.

Safe to re-run: it only adds couples that aren't already there by name, and it
only creates the aired weeks if no weeks exist yet.
"""
from __future__ import annotations

import sys

import cast_data
import db


def main() -> int:
    conn = db.connect()
    db.init_db(conn)

    couples, weeks = cast_data.seed(conn)
    db.set_setting(conn, "cast_seeded", "1")
    conn.commit()

    total = len(cast_data.CAST)
    print(f"Added {couples} couples ({total - couples} were already there).")
    if weeks:
        numbers = ", ".join(str(n) for n, _, _ in cast_data.AIRED)
        print(f"Created weeks {numbers} as UNCOUNTED drafts.")
        print("Check each on the Weeks page, then tick 'Count this week' to score it.")
    else:
        print("Weeks already exist, left alone.")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
