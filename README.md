# Dancing with the Stars Fantasy

A small self-hosted league tracker for Laura, Madison and Deborah. Four couples
each, points for surviving the week and for the big moments, and a running
ranking that recalculates itself every time you load a page.

No login. Anyone with the link can see the standings and enter results.

---

## Running it

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe app.py
```

Then open <http://127.0.0.1:5000>. On macOS/Linux use `.venv/bin/python` instead.

### Want to see it working before the real draft?

```bash
.venv/Scripts/python.exe demo.py
```

That seeds a fake half-played season into `data/demo.db` (a separate file — your
real league is untouched) and serves it on <http://127.0.0.1:5001>.

### On your server — Docker Compose

```bash
git clone https://github.com/Ty1999ler/DWTS.git
cd DWTS
docker compose up -d --build
```

No Python needed on the host. Serves on port **8035**; to change it, drop a
`.env` next to `docker-compose.yml` with `DWTS_PORT=9000`.

Updating after a change:

```bash
git pull && docker compose up -d --build
```

The database lives in `./data` on the host, bind-mounted in, so rebuilds never
touch it and a backup is copying that folder. `restart: unless-stopped` brings
it back after a reboot. Put nginx or Caddy in front for TLS and a hostname.

### On your server — without Docker

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/gunicorn -w 1 -b 0.0.0.0:8035 app:app
```

Check the port is free first with `ss -tlnp | grep :8035` — empty means free.
One worker is deliberate: ample for three people, and it keeps a single process
talking to the SQLite file.

Environment variables:

| Variable | Default | What it does |
|---|---|---|
| `DWTS_DB` | `data/league.db` | Where the database file lives |
| `DWTS_PORT` | `5000` locally, `8035` in Compose | Port for `python app.py`, and the host port in `docker-compose.yml`. With bare gunicorn, set it in `-b` instead |
| `DWTS_HOST` | `127.0.0.1` | Set to `0.0.0.0` to accept outside connections |
| `DWTS_SECRET` | random each start | Signs the "saved" banners. Set it if you run more than one worker |

Everything is in one SQLite file. Back it up by copying `data/league.db`, or
grab a JSON snapshot from the **Download a backup** link in the footer.

---

## How a season runs

0. **Load the cast** (already done for season 35):

   ```bash
   .venv/Scripts/python.exe load_cast.py
   ```

   Puts all 16 season 35 couples on the draft board, undrafted, and creates the
   two premiere weeks as **uncounted drafts** with their eliminations pencilled
   in. Safe to re-run — it skips couples that already exist and won't touch
   weeks you've created. Edit `CAST` in that file for a future season.

1. **Draft** — assign four couples to each player. Twelve of the sixteen get
   picked; the rest sit in the pool and score for nobody. Reassign any time;
   points follow the couple, not the slot.
2. **After each results show** — Weeks → *Add a week* → tick who went home and
   who topped the leaderboard, optionally type in the judges' scores, then tick
   **Count this week in the standings**. A week left unticked is a draft and
   scores nothing, so you can prep it during the show and commit it after.
   Double eliminations and tied top scores are just extra ticks.
3. **Finale** — tick everyone who reached it, then pick the winner.

Made a mistake in week 3? Fix week 3. Every total, chart and ranking is derived
from the weekly entries on each page load, so corrections ripple forward on
their own.

## Scoring

| Event | Default | Notes |
|---|---|---|
| Survived the week | **+1** | Every completed week the couple isn't eliminated |
| Highest score of the night | **+1** | Tick as many couples as tie for it — they all score |
| First perfect score of the season | **+2** | Once, league-wide. Awarding it to someone new takes it off the previous holder |
| Made the finale | **+1** | Tick as many finalists as there are — two, three, four |
| Won the mirrorball | **+2** | One couple, and they count as a finalist automatically |
| Eliminated | **0** | Set it negative on the Settings page if going home should hurt |

Every value is editable under **Settings**, along with the league name, couples
per player, and the player list. Changing one recalculates the whole season
instantly — nothing needs re-entering.

**Judges' scores are optional and never become fantasy points.** They're logged
so each couple's page can show how they've been doing with the judges over time,
and so the week page can offer to work out "highest score of the night" for you
and flag a possible first perfect score.

## What's where

| File | |
|---|---|
| `app.py` | Routes and form handling |
| `scoring.py` | The scoring engine — all the league rules live here |
| `db.py` | SQLite schema, defaults, settings |
| `charts.py` | Server-rendered SVG charts (no CDN, works offline) |
| `templates/` | Pages |
| `static/` | One stylesheet, one small script (theme toggle + chart hover) |
| `docker-compose.yml` | The server deployment — `docker compose up -d --build` |
| `load_cast.py` | The real season 35 cast — edit this for a future season |
| `test_league.py` | Plays a whole fake season through the real routes and checks the maths |
| `demo.py` | Optional sample league |

## Photos

Each couple shows their initials in the colour of whoever drafted them. To use a
real photo instead, paste an image URL into the **Photo URL** column on the Draft
page. If the URL is dead or mistyped the avatar quietly falls back to initials,
so a broken link never leaves a blank circle.

Photos are hotlinked, not copied — if you want them to survive the source site
reorganising, save the images into `static/` yourself and use a
`/static/filename.jpg` path.

Run the tests with:

```bash
.venv/Scripts/python.exe test_league.py
```
