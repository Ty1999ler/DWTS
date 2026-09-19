"""The season's cast, and the code that seeds it into a fresh database.

A brand new league loads this automatically on first start, so a clean
``docker compose up`` gives you a populated draft board with nothing to run by
hand. For a future season, replace ``CAST`` and ``AIRED`` below.

Season 35 cast cross-checked against two sources that agree on all sixteen
pairings:
  https://en.wikipedia.org/wiki/Dancing_with_the_Stars_(American_TV_series)_season_35
  https://abc7ny.com/post/dancing-stars-season-35-cast-full-celebrity-lineup-pro-partners/19777056/
"""
from __future__ import annotations

import sqlite3

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

# Weeks that had already aired when this was written, as (number, theme,
# [eliminated]). Created UNCOUNTED so nothing scores until a human opens each
# one, checks it against what actually happened, and ticks "count this week".
AIRED = [
    (1, "Premiere Night 1", ["Conner Leavitt"]),
    (2, "Premiere Night 2", ["Sarah Jane Nader"]),
]


def seed(conn: sqlite3.Connection) -> tuple[int, int]:
    """Add any missing couples, and the aired weeks if there are none yet.

    Idempotent: couples already present by name are left alone, and existing
    weeks are never touched. Returns (couples added, weeks added).
    """
    existing = {
        r["celebrity"].casefold() for r in conn.execute("SELECT celebrity FROM couples")
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

    weeks_added = 0
    if conn.execute("SELECT COUNT(*) FROM weeks").fetchone()[0] == 0:
        ids = {
            r["celebrity"]: r["id"]
            for r in conn.execute("SELECT id, celebrity FROM couples")
        }
        for number, label, eliminated in AIRED:
            cur = conn.execute(
                "INSERT INTO weeks (number, label, completed) VALUES (?, ?, 0)",
                (number, label),
            )
            for celebrity in eliminated:
                if celebrity in ids:
                    conn.execute(
                        "INSERT INTO week_couples (week_id, couple_id, eliminated) "
                        "VALUES (?, ?, 1)",
                        (cur.lastrowid, ids[celebrity]),
                    )
            weeks_added += 1

    return added, weeks_added
