"""Load the real Dancing with the Stars season 35 cast into the league.

    python load_cast.py

Safe to re-run: it only adds couples whose celebrity isn't already in the
database, and it only creates the premiere weeks if no weeks exist yet.

Cast cross-checked against two sources that agree on all sixteen pairings:
  https://en.wikipedia.org/wiki/Dancing_with_the_Stars_(American_TV_series)_season_35
  https://abc7ny.com/post/dancing-stars-season-35-cast-full-celebrity-lineup-pro-partners/19777056/

Photo URLs are left blank on purpose - paste your own on the Draft page if you
want faces instead of initials. Until then each couple shows their initials in
the colour of whoever drafted them.
"""
from __future__ import annotations

import sys

import db

# (celebrity, pro partner)
CAST = [
    ("Tatyana Ali", "Jan Ravnik"),
    ("Tyler Cameron", "Sharna Burgess"),
    ("Giada De Laurentiis", "Alan Bersten"),
    ("Jenna Dewan", "Val Chmerkovskiy"),
    ("Ezra Frech", "Daniella Karagach"),
    ("Amber Glenn", "Pasha Pashkov"),
    ("Taylor Hanson", "Britt Stewart"),
    ("Maura Higgins", "Mark Ballas"),
    ("Conner Leavitt", "Adele Zaikman"),
    ("Ciara Miller", "Brandon Armstrong"),
    ("Sarah Jane Nader", "Hailey Bills"),
    ("Jackson Olson", "Emma Slater"),
    ("Guillermo Rodriguez", "Witney Carson"),
    ("Harry Shum Jr.", "Jenna Johnson"),
    ("Julia Stiles", "Ezra Sosa"),
    ("Connor Wood", "Rylee Arnold"),
]

# The two-night premiere that has already aired. Created as UNCOUNTED drafts -
# open each one, check it against what actually happened, then tick
# "Count this week in the standings".
AIRED = [
    (1, "Premiere Night 1", ["Conner Leavitt"]),
    (2, "Premiere Night 2", ["Sarah Jane Nader"]),
]


def main() -> int:
    conn = db.connect()
    db.init_db(conn)

    existing = {
        r["celebrity"].casefold()
        for r in conn.execute("SELECT celebrity FROM couples")
    }
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM couples"
    ).fetchone()[0]

    added = 0
    for celebrity, pro in CAST:
        if celebrity.casefold() in existing:
            continue
        conn.execute(
            "INSERT INTO couples (celebrity, pro, player_id, sort_order) "
            "VALUES (?, ?, NULL, ?)",
            (celebrity, pro, next_order),
        )
        next_order += 1
        added += 1

    conn.commit()
    print(f"Added {added} couples ({len(CAST) - added} were already there).")

    if conn.execute("SELECT COUNT(*) FROM weeks").fetchone()[0]:
        print("Weeks already exist, leaving them alone.")
        conn.close()
        return 0

    ids = {r["celebrity"]: r["id"] for r in conn.execute("SELECT id, celebrity FROM couples")}
    for number, label, eliminated in AIRED:
        cur = conn.execute(
            "INSERT INTO weeks (number, label, completed) VALUES (?, ?, 0)",
            (number, label),
        )
        for celebrity in eliminated:
            conn.execute(
                "INSERT INTO week_couples (week_id, couple_id, eliminated) VALUES (?, ?, 1)",
                (cur.lastrowid, ids[celebrity]),
            )
    conn.commit()
    conn.close()

    print(f"Created weeks {', '.join(str(n) for n, _, _ in AIRED)} as UNCOUNTED drafts.")
    print("Check each one on the Weeks page, then tick 'Count this week' to score it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
