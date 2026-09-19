"""The scoring engine.

Everything the app displays is derived here from the raw weekly entries, so a
correction to week 3 automatically ripples through every total, chart and
ranking. Nothing is stored pre-computed.

Scoring rules (all point values come from Settings):
  * a couple earns ``pts_survive`` for every completed week they are not eliminated
  * the week they go home they earn ``pts_eliminated`` instead (0 by default)
  * ``pts_highest`` for having the highest judges' score of the night
  * ``pts_perfect`` for the first perfect score of the season (once, league-wide)
  * ``pts_finale`` for reaching the finale
  * ``pts_win``    for winning the whole thing

Judge scores are logged for interest only and never become fantasy points.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from db import as_number, get_settings

# Categorical slots 1-8 from the validated palette, in fixed order. Slots are
# assigned by draft order and never recycled, so a player keeps their colour
# even when the standings shuffle.
SERIES_COLORS = [
    ("#2a78d6", "#3987e5"),  # blue
    ("#eb6834", "#d95926"),  # orange
    ("#1baf7a", "#199e70"),  # aqua
    ("#eda100", "#c98500"),  # yellow
    ("#e87ba4", "#d55181"),  # magenta
    ("#008300", "#008300"),  # green
    ("#4a3aa7", "#9085e9"),  # violet
    ("#e34948", "#e66767"),  # red
]

REASON_LABELS = {
    "survive": "Survived the week",
    "eliminated": "Eliminated",
    "highest": "Highest score of the night",
    "perfect": "First perfect score of the season",
    "finale": "Made the finale",
    "win": "Won the mirrorball",
}


@dataclass
class LedgerEntry:
    week_number: int | None
    week_label: str
    reason: str
    points: float
    note: str = ""

    @property
    def label(self) -> str:
        return REASON_LABELS.get(self.reason, self.reason)


@dataclass
class Couple:
    id: int
    celebrity: str
    pro: str
    photo_url: str
    player_id: int | None
    made_finale: bool
    won: bool
    ledger: list[LedgerEntry] = field(default_factory=list)
    judge_scores: list[tuple[int, float]] = field(default_factory=list)
    eliminated_week: int | None = None
    cumulative: list[float] = field(default_factory=list)
    player_name: str = ""
    series_index: int = 1

    @property
    def name(self) -> str:
        return f"{self.celebrity} & {self.pro}" if self.pro else self.celebrity

    @property
    def total(self) -> float:
        return sum(e.points for e in self.ledger)

    @property
    def status(self) -> str:
        if self.won:
            return "Mirrorball champion"
        if self.eliminated_week is not None:
            return f"Eliminated week {self.eliminated_week}"
        if self.made_finale:
            return "In the finale"
        return "Still dancing"

    @property
    def is_out(self) -> bool:
        return self.eliminated_week is not None


@dataclass
class Player:
    id: int
    name: str
    color: str
    color_dark: str
    series_index: int = 1
    couples: list[Couple] = field(default_factory=list)
    cumulative: list[float] = field(default_factory=list)
    rank: int = 1

    @property
    def total(self) -> float:
        return sum(c.total for c in self.couples)

    @property
    def alive(self) -> int:
        return sum(1 for c in self.couples if not c.is_out)

    def breakdown(self) -> dict[str, float]:
        out = {k: 0.0 for k in REASON_LABELS}
        for couple in self.couples:
            for entry in couple.ledger:
                out[entry.reason] = out.get(entry.reason, 0.0) + entry.points
        return out


@dataclass
class Season:
    players: list[Player]
    couples: list[Couple]
    weeks: list[sqlite3.Row]
    completed_weeks: list[sqlite3.Row]
    settings: dict[str, str]
    points: dict[str, float]
    unassigned: list[Couple] = field(default_factory=list)
    perfect_claimed_by: Couple | None = None

    @property
    def week_labels(self) -> list[str]:
        return [f"W{w['number']}" for w in self.completed_weeks]

    def couple(self, couple_id: int) -> Couple | None:
        return next((c for c in self.couples if c.id == couple_id), None)


def point_values(settings: dict[str, str]) -> dict[str, float]:
    return {
        "survive": as_number(settings["pts_survive"], 1),
        "eliminated": as_number(settings["pts_eliminated"], 0),
        "highest": as_number(settings["pts_highest"], 1),
        "perfect": as_number(settings["pts_perfect"], 2),
        "finale": as_number(settings["pts_finale"], 1),
        "win": as_number(settings["pts_win"], 2),
    }


def build_season(conn: sqlite3.Connection) -> Season:
    settings = get_settings(conn)
    pts = point_values(settings)

    weeks = conn.execute("SELECT * FROM weeks ORDER BY number").fetchall()
    completed = [w for w in weeks if w["completed"]]

    entries: dict[tuple[int, int], sqlite3.Row] = {
        (r["week_id"], r["couple_id"]): r
        for r in conn.execute("SELECT * FROM week_couples").fetchall()
    }

    couples: list[Couple] = []
    for row in conn.execute(
        "SELECT * FROM couples ORDER BY sort_order, id"
    ).fetchall():
        couples.append(
            Couple(
                id=row["id"],
                celebrity=row["celebrity"],
                pro=row["pro"],
                photo_url=row["photo_url"],
                player_id=row["player_id"],
                made_finale=bool(row["made_finale"]),
                won=bool(row["won"]),
            )
        )

    perfect_claimed_by = None

    for couple in couples:
        # The first completed week the couple was marked eliminated wins, even
        # if a later week still has a stale checkbox on it.
        for week in completed:
            entry = entries.get((week["id"], couple.id))
            if entry and entry["eliminated"]:
                couple.eliminated_week = week["number"]
                break

        running = 0.0
        for week in completed:
            if couple.eliminated_week is not None and week["number"] > couple.eliminated_week:
                couple.cumulative.append(running)
                continue

            entry = entries.get((week["id"], couple.id))
            label = week["label"] or f"Week {week['number']}"

            if entry and entry["eliminated"]:
                couple.ledger.append(
                    LedgerEntry(week["number"], label, "eliminated", pts["eliminated"])
                )
            else:
                couple.ledger.append(
                    LedgerEntry(week["number"], label, "survive", pts["survive"])
                )

            if entry and entry["highest"]:
                note = ""
                if entry["judge_score"] is not None:
                    note = f"{entry['judge_score']:g} from the judges"
                couple.ledger.append(
                    LedgerEntry(week["number"], label, "highest", pts["highest"], note)
                )

            if entry and entry["perfect"]:
                perfect_claimed_by = couple
                couple.ledger.append(
                    LedgerEntry(week["number"], label, "perfect", pts["perfect"])
                )

            if entry and entry["judge_score"] is not None:
                couple.judge_scores.append((week["number"], float(entry["judge_score"])))

            running = sum(
                e.points for e in couple.ledger if (e.week_number or 0) <= week["number"]
            )
            couple.cumulative.append(running)

        # Season-end bonuses land on the last completed week so they show up on
        # the chart rather than floating outside it.
        last = completed[-1] if completed else None
        last_number = last["number"] if last else None
        last_label = (last["label"] or f"Week {last['number']}") if last else "Finale"

        if couple.made_finale:
            couple.ledger.append(
                LedgerEntry(last_number, last_label, "finale", pts["finale"])
            )
        if couple.won:
            couple.ledger.append(LedgerEntry(last_number, last_label, "win", pts["win"]))
        if (couple.made_finale or couple.won) and couple.cumulative:
            couple.cumulative[-1] = couple.total

    players: list[Player] = []
    for i, row in enumerate(
        conn.execute("SELECT * FROM players ORDER BY sort_order, id").fetchall()
    ):
        light, dark = SERIES_COLORS[i % len(SERIES_COLORS)]
        player = Player(
            id=row["id"],
            name=row["name"],
            color=light,
            color_dark=dark,
            series_index=i % len(SERIES_COLORS) + 1,
        )
        player.couples = [c for c in couples if c.player_id == player.id]
        for couple in player.couples:
            couple.player_name = player.name
            couple.series_index = player.series_index
        player.cumulative = [
            sum(c.cumulative[i] for c in player.couples if i < len(c.cumulative))
            for i in range(len(completed))
        ]
        players.append(player)

    # Rank by total, sharing a rank on a tie.
    for player in sorted(players, key=lambda p: -p.total):
        better = sum(1 for other in players if other.total > player.total)
        player.rank = better + 1

    return Season(
        players=players,
        couples=couples,
        weeks=weeks,
        completed_weeks=completed,
        settings=settings,
        points=pts,
        unassigned=[c for c in couples if c.player_id is None],
        perfect_claimed_by=perfect_claimed_by,
    )


def standings(season: Season) -> list[Player]:
    """Players ordered for display: points desc, then couples still in, then name."""
    return sorted(season.players, key=lambda p: (-p.total, -p.alive, p.name.lower()))
