"""Optional: spin up a throwaway league with a half-played sample season.

    python demo.py

Writes to ``data/demo.db`` and never touches the real ``data/league.db``, so
you can show Laura, Madison and Deborah how it works before the real draft.
Delete ``data/demo.db`` whenever you're done. The cast below is invented.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEMO_DB = BASE / "data" / "demo.db"
os.environ.setdefault("DWTS_DB", str(DEMO_DB))
# The demo has its own invented cast; don't let the real season seed on top.
os.environ.setdefault("DWTS_NO_SEED", "1")

import db  # noqa: E402
from app import app  # noqa: E402

CAST = {
    "Laura": [
        ("Nina Alvarez", "Marek Novak"),
        ("Theo Bright", "Sasha Lind"),
        ("Priya Raman", "Andre Coste"),
        ("Walt Hobbes", "Gia Moreau"),
    ],
    "Madison": [
        ("Imani Cole", "Luca Ferri"),
        ("Dex Farrow", "Mira Volkov"),
        ("Soo-jin Park", "Emil Nyberg"),
        ("Rafe Dunbar", "Talia Ruiz"),
    ],
    "Deborah": [
        ("Cleo Vance", "Bjorn Aas"),
        ("Marcus Reed", "Yuki Tanaka"),
        ("Etta Shaw", "Pablo Cruz"),
        ("Gideon Pike", "Nadia Petrova"),
    ],
}

# week -> (theme, eliminated, highest, perfect, {couple: judges' score})
SEASON = [
    (1, "Premiere Night", ["Walt Hobbes"], ["Imani Cole"], None,
     {"Imani Cole": 24, "Cleo Vance": 23, "Nina Alvarez": 21, "Walt Hobbes": 15}),
    (2, "Latin Night", ["Rafe Dunbar"], ["Cleo Vance"], None,
     {"Cleo Vance": 27, "Imani Cole": 26, "Etta Shaw": 22, "Rafe Dunbar": 17}),
    (3, "Disney Night", ["Priya Raman"], ["Cleo Vance"], None,
     {"Cleo Vance": 29, "Nina Alvarez": 26, "Imani Cole": 25, "Priya Raman": 19}),
    (4, "Motown Night", ["Soo-jin Park"], ["Cleo Vance"], "Cleo Vance",
     {"Cleo Vance": 30, "Theo Bright": 27, "Marcus Reed": 26, "Soo-jin Park": 21}),
    (5, "Halloween Night", ["Gideon Pike"], ["Nina Alvarez", "Cleo Vance"], None,
     {"Nina Alvarez": 29, "Cleo Vance": 29, "Dex Farrow": 24, "Gideon Pike": 22}),
    (6, "Semi-final", ["Marcus Reed"], ["Nina Alvarez"], None,
     {"Nina Alvarez": 30, "Cleo Vance": 29, "Theo Bright": 28, "Marcus Reed": 25}),
]


def seed() -> None:
    DEMO_DB.parent.mkdir(parents=True, exist_ok=True)
    if DEMO_DB.exists():
        DEMO_DB.unlink()

    conn = db.connect()
    db.init_db(conn)
    players = {r["name"]: r["id"] for r in conn.execute("SELECT * FROM players")}

    couples: dict[str, int] = {}
    order = 0
    for owner, cast in CAST.items():
        for celebrity, pro in cast:
            cur = conn.execute(
                "INSERT INTO couples (celebrity, pro, player_id, sort_order) "
                "VALUES (?, ?, ?, ?)",
                (celebrity, pro, players[owner], order),
            )
            couples[celebrity] = cur.lastrowid
            order += 1

    out: set[str] = set()
    for number, theme, eliminated, highest, perfect, scores in SEASON:
        cur = conn.execute(
            "INSERT INTO weeks (number, label, completed) VALUES (?, ?, 1)",
            (number, theme),
        )
        week_id = cur.lastrowid
        for celebrity, couple_id in couples.items():
            if celebrity in out:
                continue
            conn.execute(
                "INSERT INTO week_couples "
                "(week_id, couple_id, judge_score, eliminated, highest, perfect) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    week_id,
                    couple_id,
                    scores.get(celebrity),
                    1 if celebrity in eliminated else 0,
                    1 if celebrity in highest else 0,
                    1 if celebrity == perfect else 0,
                ),
            )
        out.update(eliminated)

    # Finale still to come: three couples left, nobody crowned yet.
    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed()
    print(f"Demo league seeded at {DEMO_DB}")
    print("Open http://127.0.0.1:5001 — this is sample data, not your real league.")
    app.run(host="127.0.0.1", port=int(os.environ.get("DWTS_PORT", 5001)), debug=False)
