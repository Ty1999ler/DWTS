"""Dancing with the Stars fantasy league - Laura vs. Madison vs. Deborah.

Run locally:      python app.py
Run on a server:  gunicorn -w 2 -b 0.0.0.0:8000 app:app     (waitress-serve on Windows)
"""
from __future__ import annotations

import os
import secrets

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

import charts
import db
from scoring import build_season, standings

app = Flask(__name__)
# Only used to sign the "saved" banners. A fresh random key each start is fine;
# set DWTS_SECRET if you'd rather it survive a restart (or run several workers).
app.secret_key = os.environ.get("DWTS_SECRET") or secrets.token_hex(32)


# --------------------------------------------------------------------------- db


def get_db():
    if "db" not in g:
        g.db = db.connect()
        db.init_db(g.db)
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.context_processor
def inject_globals():
    settings = db.get_settings(get_db())
    return {
        "league_name": settings["league_name"],
        "season_label": settings["season_label"],
        "sparkline": charts.sparkline,
    }


@app.template_filter("pts")
def fmt_points(value) -> str:
    """Drop the trailing .0 so whole points read as whole numbers."""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _int(name: str, default: int | None = None) -> int | None:
    raw = request.form.get(name, "").strip()
    if raw in ("", "none", "None"):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_or_none(name: str) -> float | None:
    raw = request.form.get(name, "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


# ------------------------------------------------------------------ main views


@app.route("/")
def index():
    conn = get_db()
    season = build_season(conn)
    table = standings(season)

    chart = charts.cumulative_chart(
        [
            {
                "name": p.name,
                "color": p.color,
                "color_dark": p.color_dark,
                "values": p.cumulative,
            }
            for p in season.players
            if p.couples
        ],
        season.week_labels,
    )
    return render_template(
        "standings.html",
        season=season,
        table=table,
        chart=chart,
        drafting=bool(season.unassigned) or not season.completed_weeks,
    )


@app.route("/teams")
def teams():
    season = build_season(get_db())
    return render_template("teams.html", season=season, table=standings(season))


@app.route("/couple/<int:couple_id>")
def couple_detail(couple_id: int):
    season = build_season(get_db())
    couple = season.couple(couple_id)
    if couple is None:
        flash("That couple is not in the league.", "warn")
        return redirect(url_for("draft"))

    judge_chart = None
    if len(couple.judge_scores) > 1:
        judge_chart = charts.cumulative_chart(
            [
                {
                    "name": "Score",
                    "color": "#2a78d6",
                    "color_dark": "#3987e5",
                    "values": [v for _, v in couple.judge_scores],
                }
            ],
            [f"W{n}" for n, _ in couple.judge_scores],
            # Judges' scores live in a narrow band well above zero.
            zero_base=False,
        )
    return render_template(
        "couple.html", season=season, couple=couple, judge_chart=judge_chart
    )


# ----------------------------------------------------------------------- draft


@app.route("/draft")
def draft():
    season = build_season(get_db())
    return render_template(
        "draft.html",
        season=season,
        roster_size=int(db.as_number(season.settings["roster_size"], 4)),
    )


@app.post("/draft/couple/add")
def add_couple():
    conn = get_db()
    celebrity = request.form.get("celebrity", "").strip()
    if not celebrity:
        flash("A couple needs a celebrity name.", "warn")
        return redirect(url_for("draft"))
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM couples"
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO couples (celebrity, pro, photo_url, player_id, sort_order) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            celebrity,
            request.form.get("pro", "").strip(),
            request.form.get("photo_url", "").strip(),
            _int("player_id"),
            next_order,
        ),
    )
    conn.commit()
    flash(f"Added {celebrity}.", "ok")
    return redirect(url_for("draft"))


@app.post("/draft/save")
def save_draft():
    conn = get_db()
    for couple_id in request.form.getlist("couple_ids", type=int):
        celebrity = request.form.get(f"celebrity_{couple_id}", "").strip()
        if not celebrity:
            continue
        conn.execute(
            "UPDATE couples SET celebrity = ?, pro = ?, photo_url = ?, player_id = ? "
            "WHERE id = ?",
            (
                celebrity,
                request.form.get(f"pro_{couple_id}", "").strip(),
                request.form.get(f"photo_{couple_id}", "").strip(),
                _int(f"player_{couple_id}"),
                couple_id,
            ),
        )
    conn.commit()
    flash("Draft board saved.", "ok")
    return redirect(url_for("draft"))


@app.post("/draft/couple/<int:couple_id>/delete")
def delete_couple(couple_id: int):
    conn = get_db()
    conn.execute("DELETE FROM couples WHERE id = ?", (couple_id,))
    conn.commit()
    flash("Couple removed.", "ok")
    return redirect(url_for("draft"))


# --------------------------------------------------------------------- players


@app.post("/players/add")
def add_player():
    conn = get_db()
    name = request.form.get("name", "").strip()
    if not name:
        flash("A player needs a name.", "warn")
        return redirect(url_for("settings"))
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM players"
    ).fetchone()[0]
    try:
        conn.execute(
            "INSERT INTO players (name, sort_order) VALUES (?, ?)", (name, next_order)
        )
        conn.commit()
        flash(f"{name} joined the league.", "ok")
    except Exception:
        flash(f"{name} is already in the league.", "warn")
    return redirect(url_for("settings"))


@app.post("/players/<int:player_id>/delete")
def delete_player(player_id: int):
    conn = get_db()
    conn.execute("UPDATE couples SET player_id = NULL WHERE player_id = ?", (player_id,))
    conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
    conn.commit()
    flash("Player removed; their couples are back in the pool.", "ok")
    return redirect(url_for("settings"))


# ----------------------------------------------------------------------- weeks


@app.route("/weeks")
def weeks():
    conn = get_db()
    season = build_season(conn)
    names = {c.id: c.celebrity for c in season.couples}

    summaries: dict[int, dict] = {
        w["id"]: {"eliminated": [], "highest": [], "perfect": [], "scored": 0}
        for w in season.weeks
    }
    for r in conn.execute("SELECT * FROM week_couples").fetchall():
        bucket = summaries.get(r["week_id"])
        if bucket is None:
            continue
        name = names.get(r["couple_id"], "?")
        if r["eliminated"]:
            bucket["eliminated"].append(name)
        if r["highest"]:
            bucket["highest"].append(name)
        if r["perfect"]:
            bucket["perfect"].append(name)
        if r["judge_score"] is not None:
            bucket["scored"] += 1

    next_number = max((w["number"] for w in season.weeks), default=0) + 1
    return render_template(
        "weeks.html", season=season, next_number=next_number, summaries=summaries
    )


@app.post("/weeks/add")
def add_week():
    conn = get_db()
    number = _int("number")
    if number is None:
        flash("Give the week a number.", "warn")
        return redirect(url_for("weeks"))
    existing = conn.execute("SELECT id FROM weeks WHERE number = ?", (number,)).fetchone()
    if existing:
        return redirect(url_for("week_detail", week_id=existing["id"]))
    cur = conn.execute(
        "INSERT INTO weeks (number, label) VALUES (?, ?)",
        (number, request.form.get("label", "").strip()),
    )
    conn.commit()
    return redirect(url_for("week_detail", week_id=cur.lastrowid))


@app.route("/week/<int:week_id>")
def week_detail(week_id: int):
    conn = get_db()
    week = conn.execute("SELECT * FROM weeks WHERE id = ?", (week_id,)).fetchone()
    if week is None:
        flash("No such week.", "warn")
        return redirect(url_for("weeks"))

    season = build_season(conn)
    entries = {
        r["couple_id"]: r
        for r in conn.execute(
            "SELECT * FROM week_couples WHERE week_id = ?", (week_id,)
        ).fetchall()
    }
    # Couples still in the running going into this week, plus anyone who
    # already has an entry saved against it.
    eligible = [
        c
        for c in season.couples
        if c.player_id is not None
        and (
            c.eliminated_week is None
            or c.eliminated_week >= week["number"]
            or c.id in entries
        )
    ]

    perfect_value = db.as_number(season.settings["perfect_score_value"], 30)
    perfect_candidates = [
        c
        for c in eligible
        if entries.get(c.id)
        and entries[c.id]["judge_score"] is not None
        and entries[c.id]["judge_score"] >= perfect_value
    ]

    return render_template(
        "week.html",
        season=season,
        week=week,
        entries=entries,
        eligible=eligible,
        perfect_value=perfect_value,
        perfect_candidates=perfect_candidates,
    )


@app.post("/week/<int:week_id>/save")
def save_week(week_id: int):
    conn = get_db()
    week = conn.execute("SELECT * FROM weeks WHERE id = ?", (week_id,)).fetchone()
    if week is None:
        flash("No such week.", "warn")
        return redirect(url_for("weeks"))

    conn.execute(
        "UPDATE weeks SET label = ?, completed = ? WHERE id = ?",
        (
            request.form.get("label", "").strip(),
            1 if request.form.get("completed") else 0,
            week_id,
        ),
    )

    couple_ids = request.form.getlist("couple_ids", type=int)
    rows = []
    for couple_id in couple_ids:
        rows.append(
            {
                "couple_id": couple_id,
                "judge_score": _float_or_none(f"score_{couple_id}"),
                "eliminated": 1 if request.form.get(f"elim_{couple_id}") else 0,
                "highest": 1 if request.form.get(f"high_{couple_id}") else 0,
                "perfect": 1 if request.form.get(f"perfect_{couple_id}") else 0,
            }
        )

    # "Highest score of the night" derived from the judge scores entered above.
    if request.form.get("auto_highest"):
        scored = [r for r in rows if r["judge_score"] is not None]
        if scored:
            best = max(r["judge_score"] for r in scored)
            for r in rows:
                r["highest"] = 1 if r["judge_score"] == best else 0

    conn.execute("DELETE FROM week_couples WHERE week_id = ?", (week_id,))
    for r in rows:
        conn.execute(
            "INSERT INTO week_couples "
            "(week_id, couple_id, judge_score, eliminated, highest, perfect) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                week_id,
                r["couple_id"],
                r["judge_score"],
                r["eliminated"],
                r["highest"],
                r["perfect"],
            ),
        )

    # The first perfect score of the season happens once. If it was awarded
    # here, it cannot also be sitting on another week.
    if any(r["perfect"] for r in rows):
        conn.execute("UPDATE week_couples SET perfect = 0 WHERE week_id != ?", (week_id,))

    # Anyone eliminated this week cannot have rows in later weeks.
    gone = [r["couple_id"] for r in rows if r["eliminated"]]
    for couple_id in gone:
        conn.execute(
            "DELETE FROM week_couples WHERE couple_id = ? AND week_id IN "
            "(SELECT id FROM weeks WHERE number > ?)",
            (couple_id, week["number"]),
        )

    conn.commit()
    flash(f"Week {week['number']} saved.", "ok")
    if request.form.get("completed"):
        return redirect(url_for("index"))
    return redirect(url_for("week_detail", week_id=week_id))


@app.post("/week/<int:week_id>/delete")
def delete_week(week_id: int):
    conn = get_db()
    conn.execute("DELETE FROM week_couples WHERE week_id = ?", (week_id,))
    conn.execute("DELETE FROM weeks WHERE id = ?", (week_id,))
    conn.commit()
    flash("Week deleted.", "ok")
    return redirect(url_for("weeks"))


# ---------------------------------------------------------------------- finale


@app.route("/finale")
def finale():
    season = build_season(get_db())
    return render_template("finale.html", season=season)


@app.post("/finale/save")
def save_finale():
    conn = get_db()
    winner = _int("winner")
    finalists = set(request.form.getlist("finalist", type=int))
    if winner is not None:
        finalists.add(winner)
    conn.execute("UPDATE couples SET made_finale = 0, won = 0")
    for couple_id in finalists:
        conn.execute("UPDATE couples SET made_finale = 1 WHERE id = ?", (couple_id,))
    if winner is not None:
        conn.execute("UPDATE couples SET won = 1 WHERE id = ?", (winner,))
    conn.commit()
    flash("Finale saved.", "ok")
    return redirect(url_for("index"))


# -------------------------------------------------------------------- settings


@app.route("/settings")
def settings():
    season = build_season(get_db())
    return render_template("settings.html", season=season)


@app.post("/settings/save")
def save_settings():
    conn = get_db()
    for key in (
        "league_name",
        "season_label",
        "pts_survive",
        "pts_eliminated",
        "pts_highest",
        "pts_perfect",
        "pts_finale",
        "pts_win",
        "roster_size",
        "perfect_score_value",
    ):
        if key in request.form:
            db.set_setting(conn, key, request.form[key].strip())

    for player_id in request.form.getlist("player_ids", type=int):
        name = request.form.get(f"player_name_{player_id}", "").strip()
        if name:
            conn.execute("UPDATE players SET name = ? WHERE id = ?", (name, player_id))

    conn.commit()
    flash("Settings saved. Every score has been recalculated.", "ok")
    return redirect(url_for("settings"))


@app.route("/export.json")
def export_json():
    """A one-click backup of the whole league."""
    conn = get_db()
    return jsonify(
        {
            table: [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
            for table in ("settings", "players", "couples", "weeks", "week_couples")
        }
    )


if __name__ == "__main__":
    app.run(
        host=os.environ.get("DWTS_HOST", "127.0.0.1"),
        port=int(os.environ.get("DWTS_PORT", 5000)),
        debug=bool(os.environ.get("DWTS_DEBUG")),
    )
