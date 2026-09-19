"""End-to-end check of the scoring engine and every page.

Runs a whole fake season through the real HTTP routes against a throwaway
database, then asserts the standings. Run it with:

    python test_league.py
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DWTS_DB"] = str(TMP)

import app as application  # noqa: E402  (must follow the env var)
from db import connect, get_settings  # noqa: E402
from scoring import build_season, standings  # noqa: E402

client = application.app.test_client()
failures: list[str] = []


def check(label: str, got, want) -> None:
    if got == want:
        print(f"  ok   {label}: {got}")
    else:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")
        print(f"  FAIL {label}: got {got!r}, wanted {want!r}")


def page(path: str, expect: int = 200) -> str:
    r = client.get(path)
    if r.status_code != expect:
        failures.append(f"GET {path} -> {r.status_code}")
        print(f"  FAIL GET {path} -> {r.status_code}")
    else:
        print(f"  ok   GET {path} -> {r.status_code}")
    return r.get_data(as_text=True)


def season():
    conn = connect()
    try:
        return build_season(conn)
    finally:
        conn.close()


def player(name: str):
    return next(p for p in season().players if p.name == name)


def couple(celebrity: str):
    return next(c for c in season().couples if c.celebrity == celebrity)


print("\n1. Bootstrap")
page("/")
players = {p.name: p.id for p in season().players}
check("starting players", sorted(players), ["Deborah", "Laura", "Madison"])

print("\n2. Draft twelve couples, four each")
roster = {
    "Laura": ["Alice", "Bea", "Cara", "Dana"],
    "Madison": ["Evan", "Finn", "Gus", "Hank"],
    "Deborah": ["Iris", "Jill", "Kira", "Lena"],
}
for owner, names in roster.items():
    for name in names:
        client.post(
            "/draft/couple/add",
            data={"celebrity": name, "pro": f"Pro {name[0]}", "player_id": players[owner]},
        )
check("couples drafted", len(season().couples), 12)
check("undrafted", len(season().unassigned), 0)
check("Laura's roster", len(player("Laura").couples), 4)

print("\n3. Week 1 - Alice goes home, Evan tops the leaderboard")
client.post("/weeks/add", data={"number": 1, "label": "Premiere"})
week1 = season().weeks[0]["id"]
all_ids = [c.id for c in season().couples]
client.post(
    f"/week/{week1}/save",
    data={
        "couple_ids": all_ids,
        "label": "Premiere",
        "completed": "on",
        f"elim_{couple('Alice').id}": "on",
        f"high_{couple('Evan').id}": "on",
        f"score_{couple('Evan').id}": "27",
        f"score_{couple('Iris').id}": "24",
    },
)
check("Alice out in week 1", couple("Alice").eliminated_week, 1)
check("Alice scored nothing", couple("Alice").total, 0)
check("Evan: survived + top score", couple("Evan").total, 2)
check("Laura after week 1", player("Laura").total, 3)

print("\n4. Week 2 - Finn goes home, Iris lands the first perfect 30")
client.post("/weeks/add", data={"number": 2, "label": "Latin Night"})
week2 = [w["id"] for w in season().weeks if w["number"] == 2][0]
alive = [c.id for c in season().couples if not c.is_out]
client.post(
    f"/week/{week2}/save",
    data={
        "couple_ids": alive,
        "label": "Latin Night",
        "completed": "on",
        f"elim_{couple('Finn').id}": "on",
        f"perfect_{couple('Iris').id}": "on",
        f"score_{couple('Iris').id}": "30",
    },
)
check("Finn out in week 2", couple("Finn").eliminated_week, 2)
check("Finn kept his week 1 point", couple("Finn").total, 1)
check("Iris: 2 weeks + perfect", couple("Iris").total, 4)
check("perfect claimed by", season().perfect_claimed_by.celebrity, "Iris")

print("\n5. Week 3 saved as a draft - must not count")
client.post("/weeks/add", data={"number": 3})
week3 = [w["id"] for w in season().weeks if w["number"] == 3][0]
before = {p.name: p.total for p in season().players}
client.post(
    f"/week/{week3}/save",
    data={
        "couple_ids": [c.id for c in season().couples if not c.is_out],
        f"elim_{couple('Gus').id}": "on",
    },
)
check("uncounted week changes nothing", {p.name: p.total for p in season().players}, before)
check("Gus still shown as dancing", couple("Gus").eliminated_week, None)

print("\n6. Finale - Cara and Iris make it, Iris wins")
client.post(
    "/finale/save",
    data={"finalist": [couple("Cara").id, couple("Iris").id], "winner": couple("Iris").id},
)
check("Cara: 2 weeks + finale", couple("Cara").total, 3)
check("Iris: 2 weeks + perfect + finale + win", couple("Iris").total, 7)

print("\n7. Final standings")
check("Laura", player("Laura").total, 7)
check("Madison", player("Madison").total, 8)
check("Deborah", player("Deborah").total, 13)
check("order", [p.name for p in standings(season())], ["Deborah", "Madison", "Laura"])
check("ranks", [p.rank for p in standings(season())], [1, 2, 3])

print("\n8. Retuning the scoring recalculates everything")
client.post(
    "/settings/save",
    data={
        **{k: v for k, v in get_settings(connect()).items() if k.startswith("pts_")},
        "pts_survive": "2",
    },
)
# Each surviving week is now worth 2: Laura 3->6 for Bea/Dana... recompute directly.
check("Laura after re-tune", player("Laura").total, 13)
check("Deborah after re-tune", player("Deborah").total, 21)
client.post("/settings/save", data={"pts_survive": "1"})
check("back to normal", player("Laura").total, 7)

def highest_weeks(celebrity: str) -> list[int]:
    return [e.week_number for e in couple(celebrity).ledger if e.reason == "highest"]


def alive_ids() -> list[int]:
    return [c.id for c in season().couples if not c.is_out]


print("\n9. Week 4 - Bea and Evan tie for the highest score, both score")
client.post("/weeks/add", data={"number": 4, "label": "Disney Night"})
week4 = [w["id"] for w in season().weeks if w["number"] == 4][0]
client.post(
    f"/week/{week4}/save",
    data={
        "couple_ids": alive_ids(),
        "label": "Disney Night",
        "completed": "on",
        f"high_{couple('Bea').id}": "on",
        f"high_{couple('Evan').id}": "on",
        f"score_{couple('Bea').id}": "29",
        f"score_{couple('Evan').id}": "29",
    },
)
check("Bea took a share of the top score", highest_weeks("Bea"), [4])
check("Evan's two top scores", highest_weeks("Evan"), [1, 4])
check("Laura", player("Laura").total, 11)
check("Madison", player("Madison").total, 12)
check("Deborah", player("Deborah").total, 17)

print("\n10. Week 5 - a three-way tie worked out from the judges' scores")
client.post("/weeks/add", data={"number": 5, "label": "Halloween Night"})
week5 = [w["id"] for w in season().weeks if w["number"] == 5][0]
client.post(
    f"/week/{week5}/save",
    data={
        "couple_ids": alive_ids(),
        "label": "Halloween Night",
        "completed": "on",
        "auto_highest": "on",
        f"score_{couple('Cara').id}": "29",
        f"score_{couple('Hank').id}": "29",
        f"score_{couple('Jill').id}": "29",
        f"score_{couple('Iris').id}": "25",
    },
)
check("Cara shares the top score", highest_weeks("Cara"), [5])
check("Hank shares the top score", highest_weeks("Hank"), [5])
check("Jill shares the top score", highest_weeks("Jill"), [5])
check("Iris scored 25, so no bonus", highest_weeks("Iris"), [])
check("Laura", player("Laura").total, 15)
check("Madison", player("Madison").total, 16)
check("Deborah", player("Deborah").total, 22)

print("\n11. A three-couple finale")
client.post(
    "/finale/save",
    data={
        "finalist": [couple("Cara").id, couple("Iris").id, couple("Jill").id],
        "winner": couple("Iris").id,
    },
)
check("three finalists", sum(1 for c in season().couples if c.made_finale), 3)
check("one winner", sum(1 for c in season().couples if c.won), 1)
check("Cara: finalist bonus only", couple("Cara").made_finale and not couple("Cara").won, True)
check("Jill: 4 weeks + a shared top score + the finale bonus", couple("Jill").total, 6)
check("Laura", player("Laura").total, 15)
check("Madison", player("Madison").total, 16)
check("Deborah", player("Deborah").total, 23)

print("\n12. Every page renders")
for path in ["/", "/teams", "/weeks", "/draft", "/finale", "/settings", "/export.json"]:
    page(path)
body = page(f"/couple/{couple('Iris').id}")
check("couple page names the owner", "Deborah" in body, True)
check("couple page shows the perfect-score chip", "First perfect score" in body, True)
check("rankings page charts the season", "chart-wrap" in page("/"), True)

print("\n13. Photos, and what happens without one")


def avatar_initials(html: str, celebrity: str) -> str | None:
    m = re.search(
        r'class="avatar[^"]*"[^>]*title="' + re.escape(celebrity) + r'[^"]*">\s*([A-Z]+)',
        html,
    )
    return m.group(1) if m else None


client.post("/draft/couple/add", data={"celebrity": "Rosa Vega", "pro": "Kit Lang"})
rosa = couple("Rosa Vega")
check("added undrafted, so nobody's score moves", rosa.player_id, None)
draft_html = client.get("/draft").get_data(as_text=True)
check("no photo falls back to initials", avatar_initials(draft_html, "Rosa Vega"), "RV")

# Save a photo, then confirm the initials are still underneath it - a dead or
# mistyped URL has to degrade to initials, not to an empty circle.
current = season().couples
client.post(
    "/draft/save",
    data={
        "couple_ids": [c.id for c in current],
        **{f"celebrity_{c.id}": c.celebrity for c in current},
        **{f"pro_{c.id}": c.pro for c in current},
        **{f"player_{c.id}": (c.player_id or "") for c in current},
        f"photo_{rosa.id}": "https://example.invalid/rosa.jpg",
    },
)
check("photo url saved", couple("Rosa Vega").photo_url, "https://example.invalid/rosa.jpg")
draft_html = client.get("/draft").get_data(as_text=True)
check("photo renders as an img", "https://example.invalid/rosa.jpg" in draft_html, True)
check("a broken photo removes itself", 'onerror="this.remove()"' in draft_html, True)
check("initials still sit behind it", avatar_initials(draft_html, "Rosa Vega"), "RV")
check(
    "the whole round-trip left every team alone",
    [player(n).total for n in ("Laura", "Madison", "Deborah")],
    [15, 16, 23],
)

print("\n" + "=" * 60)
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print("  -", f)
    raise SystemExit(1)
print("All checks passed.")
