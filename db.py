"""SQLite storage for the DWTS fantasy league.

One file, one database. Everything the league knows lives in ``data/league.db``
so a backup is a single file copy.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DWTS_DB", BASE_DIR / "data" / "league.db"))

# Everything here is editable on the Settings page. These are just the values a
# brand new league starts with.
DEFAULT_SETTINGS = {
    "league_name": "Dancing with the Stars Fantasy",
    "season_label": "Season 35",
    "roster_size": "4",
    # Scoring
    "pts_survive": "1",     # couple is still in the competition after the week
    "pts_eliminated": "0",  # the week a couple goes home (make it negative for a penalty)
    "pts_highest": "1",     # highest judges' score of the night
    "pts_perfect": "2",     # the first perfect score of the whole season (once)
    "pts_finale": "1",      # bonus for reaching the finale
    "pts_win": "2",         # bonus for winning the mirrorball
    # Judge scores are logged for interest only; they never become fantasy points.
    "perfect_score_value": "30",
}

STARTING_PLAYERS = ["Laura", "Madison", "Deborah"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS couples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    celebrity   TEXT NOT NULL,
    pro         TEXT NOT NULL DEFAULT '',
    photo_url   TEXT NOT NULL DEFAULT '',
    player_id   INTEGER REFERENCES players(id) ON DELETE SET NULL,
    made_finale INTEGER NOT NULL DEFAULT 0,
    won         INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS weeks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    number    INTEGER NOT NULL UNIQUE,
    label     TEXT NOT NULL DEFAULT '',
    completed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS week_couples (
    week_id     INTEGER NOT NULL REFERENCES weeks(id)   ON DELETE CASCADE,
    couple_id   INTEGER NOT NULL REFERENCES couples(id) ON DELETE CASCADE,
    judge_score REAL,
    eliminated  INTEGER NOT NULL DEFAULT 0,
    highest     INTEGER NOT NULL DEFAULT 0,
    perfect     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (week_id, couple_id)
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Bring an older database up to the current schema, in place."""
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(couples)")}
    if columns and "photo_url" not in columns:
        conn.execute(
            "ALTER TABLE couples ADD COLUMN photo_url TEXT NOT NULL DEFAULT ''"
        )


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
    if conn.execute("SELECT COUNT(*) FROM players").fetchone()[0] == 0:
        for i, name in enumerate(STARTING_PLAYERS):
            conn.execute(
                "INSERT INTO players (name, sort_order) VALUES (?, ?)", (name, i)
            )
    conn.commit()


def get_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = dict(DEFAULT_SETTINGS)
    settings.update({r["key"]: r["value"] for r in rows})
    return settings


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def as_number(value: str, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
