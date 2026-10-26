# 📍 TLV Bot

A web chatbot that recommends the closest spot from your own curated Google My Maps
map of favorite Tel Aviv food places. Tell it what you're craving, share your
location, and it finds the nearest match with a one-tap navigation link.

This started as a WhatsApp bot (Twilio + Azure PostGIS Postgres); it's now a
lightweight web app that runs for roughly $15/month.

## ✨ Features

* **Free-text cravings:** "ramen", "something cheap", "coffee near here" -
  Claude (Haiku 4.5) matches your message to a category from your map, plus an
  optional price tier and dietary tag. English and Hebrew.
* **Honest replies:** when it can't honour a request ("open now", "vegan" with
  no vegan pins, a night club) it says so instead of returning unrelated
  places, and logs the request so the curator can see what the list lacks.
* **Nearest-match search:** MongoDB's geospatial `$geoNear` finds the closest
  places in that category to your set location, 3 at a time with "Show more"
  and follow-ups like "something else" or "cheaper". Places likely to be closed
  right now, or outdoor spots in the rain, sort after the rest.
* **Results first, travel times after:** cards appear at once with the
  distance (in metres under 1 km); walking or driving times from OSRM fill in
  a moment later, so a slow routing service never delays the answer.
* **One-tap navigation:** a Google Maps directions link on every card (a plain
  deep link, no API key or billing), an Instagram link where available, a
  WhatsApp share button, and an optional results map (Leaflet + OpenStreetMap).
* **Your own location:** live geolocation, or a typed address, coordinates or
  Google Maps link in Tel Aviv-Yafo, Ramat Gan and Givatayim, with a "Did you
  mean ...?" suggestion for misspelt streets.
* **Auto-updating database:** one script pulls the latest pins straight from
  your public Google My Maps map, on a daily schedule in production. Values
  added by hand in MongoDB Atlas (`instagram_url`) survive syncs.
* **Optional accounts (Google Sign-In):** nobody has to sign in to use the
  chatbot. Signed-in users get favorites, up to 5 saved addresses and a
  "Suggest a spot" form (private to the curator, sanitised, rate limited), and
  can delete their account and everything stored for it.
* **Private curator signals:** visitors can flag a place as closed, in the
  wrong category, or "I'd go back". These are anonymous, never shown to other
  visitors, and read with a script.
* **Installable PWA** with a light/dark theme, full RTL support, and
  `/privacy`, `/about` and 404 pages.

## 🏗️ Architecture

* **Frontend:** React + TypeScript (`frontend/`), built with Vite straight into
  `static/` (content-hashed filenames, cached forever; `index.html` itself is
  always revalidated so it picks up the latest build). The results map lives
  in its own lazy-loaded chunk.
* **Backend:** FastAPI (Python 3.11), serving both the built page and a JSON
  API (`/api/chat`, `/api/etas`, `/api/favorites`, `/api/suggestions`, ...),
  with per-IP rate limits and server-side input sanitising.
* **Database:** MongoDB Atlas, free-forever M0 tier (512MB). A `2dsphere` index
  on each place's location powers the nearest-match queries.
* **NLU:** Anthropic API, `claude-haiku-4-5` - one small tool-call per chat
  message to match free text to a known category. At personal-project volume
  this runs about $1-2/month.
* **Auth:** Google Identity Services (ID-token flow) verified server-side,
  plus this app's own short-lived JWT access tokens (in-memory only) and
  longer-lived refresh tokens (httpOnly cookie, scoped to `/api/auth`). No
  self-managed passwords - see `CLAUDE.md` for the full design writeup.
  What is stored per account (saved addresses, favorites, suggestions) is
  described in plain language in `frontend/public/privacy.html` - update it in
  the same change as anything that alters what's stored.
* **Free public services:** OSRM for travel times, Nominatim for address
  lookup, Open-Meteo for a rain check, OpenStreetMap tiles for the map. No keys.
* **Hosting:** Azure App Service, split into a production and a staging
  environment (see `CLAUDE.md` for the full story and setup gotchas).
  Production runs on a dedicated Basic (B1) plan (~$14.45/month - the
  Free tier's 60 CPU-minute/day cap isn't viable for a live app people
  actually use); staging runs on a separate Free (F1) plan with its own
  isolated database, for testing risky changes (like auth) before they
  touch real data. Each deploys from its own branch (`main` -> production,
  `staging` -> staging) via `.github/workflows/`.
* **Data source:** a Google My Maps custom map, shared publicly, exported as
  KML on demand via its stable `mid=` URL.

For diagrams of how it all fits together (what runs where, the module map, the
code path of one chat message, and tap-to-database traces), see
[`docs/architecture.md`](docs/architecture.md).

Total running cost at personal-project scale: ~$14-15/month - production's
Basic-tier App Service plan is the one real line item; everything else
(MongoDB Atlas, staging's Free-tier App Service, OSRM routing) is free or
close to it, plus a few dollars/month for the Anthropic API.

## 🚀 Setup

### 1. Prerequisites

- Python 3.11+
- Node.js 18+ (for the frontend build)
- A MongoDB Atlas account (free M0 cluster)
- An Anthropic API key
- Your Tel Aviv food map created in [Google My Maps](https://www.google.com/maps/d/)

### 2. Share your My Maps map publicly

Open your map in My Maps -> Share -> set visibility to "Anyone with this link"
(view-only is fine). Then open the map and copy the `mid=` value from its URL
(`https://www.google.com/maps/d/edit?mid=THIS_PART&...`).

### 3. Create a free MongoDB Atlas cluster

Create an M0 (free) cluster at [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas),
create a database user, allow network access from your IP (or `0.0.0.0/0` for
simplicity on a personal project), and copy the connection string.

### 4. Environment variables

Copy `.env.example` to `.env` and fill in:

```env
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB_NAME=tlvbot
MYMAPS_ID=your_mymaps_id_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
GOOGLE_CLIENT_ID=your_google_oauth_client_id_here
JWT_SECRET=a_long_random_string_unique_per_environment
```

`GOOGLE_CLIENT_ID` comes from a Google Cloud OAuth Client ID (Identity
Services, ID-token flow - see `CLAUDE.md` for setup). It isn't secret (it
ends up in the frontend's own public code either way), but `JWT_SECRET` is -
generate a long random value and use a **different** one for local dev,
staging, and production, so signing out of one environment can never affect
another.

### 5. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate  # On Windows
pip install -r requirements.txt
```

### 6. Load your places into MongoDB

```bash
python -m scripts.sync_places
```

Re-run this any time you add/remove/move a pin on your My Maps map - it
matches places by physical proximity (so renames are handled correctly) and
removes anything no longer on the map, without touching `instagram_url`
values already stored.

**If migrating from the old CSV-based bot:** the raw KML export doesn't carry
Instagram links (those were added by hand into `data/cleaned_places.csv`).
After your first sync, backfill them once with:

```bash
python -m scripts.seed_instagram_from_csv
```

You can also add/edit `instagram_url` (or anything else) directly in the
MongoDB Atlas web UI at any time - syncing never overwrites it.

### 7. Build the frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

This builds straight into `static/` (gitignored - it's build output, not
source). Re-run it after any change under `frontend/src`. For frontend-only
iteration, `npm run dev` inside `frontend/` runs Vite's dev server on
`localhost:5173` and proxies `/api/*` to `localhost:8000`, so run the backend
(next step) alongside it.

### 8. Run locally

```bash
uvicorn backend.app:app --reload
```

Open `http://localhost:8000`.

### 9. Deploy

Two environments, each with its own App Service and its own GitHub Actions
workflow - both build the frontend (Node) and then the Python app, no manual
build steps needed:

- `.github/workflows/deploy-production.yml` - deploys on every push to
  `main`, to the production App Service.
- `.github/workflows/deploy-staging.yml` - deploys on every push to a
  `staging` branch, to a separate App Service pointed at an isolated
  database (`MONGODB_DB_NAME` set differently there - see `CLAUDE.md`).

For either App Service, in its Configuration (or "Environment variables" in
newer Portal versions) -> Application settings, set the same env vars
as above, **plus**:

```
SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

This one is easy to miss if you ever set up an App Service by hand instead
of through Azure's own "set up CI/CD" Portal wizard (which adds it for you
automatically) - without it, Azure's Oryx build system never runs `pip
install` server-side, and the app fails to start with `No module named
uvicorn` in the Log stream, not an obvious "missing config" error. Ask me
about this if it comes up again; there's a longer writeup in `CLAUDE.md`.

Then set the startup command (General settings tab, same Configuration page):

```
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

## Structure

```
backend/                                FastAPI app package.
  app.py                                  Routes, middleware, rate limits and
                                           reply text - delegates to db.py
                                           and services/
  db.py                                   MongoDB access (the data layer)
  models.py                               Schema (Pydantic) - single source
                                           of truth for a place document
  parser.py                               KML -> place dicts
  data/streets.json                       Street names for typo suggestions
  services/                               One module per concern:
    llm.py                                  Claude NLU (category, tag, price,
                                             follow-up, unsupported request)
    location.py                             Google Maps link + address lookup
    streets.py                              "Did you mean" street matching
    routing.py                              OSRM travel times
    weather.py                              Open-Meteo rain check
    auth.py                                 Google token check + JWTs
    suggestions.py                          Sanitising for suggested spots
    clientip.py                             Rate-limit key diagnostic (no IPs)
    resilience.py                           Shared cache + back-off
scripts/                                Maintenance CLI scripts, run as
  sync_places.py                          python -m scripts.<name>
  seed_instagram_from_csv.py              (one-off Instagram backfill)
  show_reports.py                         what visitors flagged (closed,
                                           wrong category, would go back)
  show_suggestions.py                     places signed-in visitors suggested
  build_street_index.py                   regenerate backend/data/streets.json
  build_icons.py                          regenerate the PWA icons
data/                                   Local data files (gitignored - your
  map.kml, cleaned_places.csv             curated list stays private)
docs/architecture.md                    Mermaid diagrams of the system
frontend/                               React + TypeScript app (source);
  src/App.tsx                             all state and handlers
  src/components/                         presentational components
  src/api.ts, i18n.ts, types.ts           API client, EN/HE strings, types
  public/                                 static pages (privacy, about, 404),
                                           manifest, service worker
static/                                 Generated by frontend's build -
                                         gitignored, don't edit by hand
tests/                                  pytest suite - conftest.py at the
                                         root adds it to sys.path and blocks
                                         any test from reaching a real DB
.github/workflows/                      deploy-production, deploy-staging
                                         (both run the tests first) and the
                                         daily sync_places job
CLAUDE.md                               Project history, decisions, roadmap
DESIGN.md                               Visual design system
```

`backend/` (not `app/`) is deliberate - `app.py` lives inside it, and a
sibling `app/` package would collide with that filename.

## Running tests

```bash
pytest
```

The frontend must be built once first (`static/` has to exist for the app to
import). A few auth tests need a `JWT_SECRET`; CI uses a dummy one:

```bash
JWT_SECRET=anything pytest
```

Tests never touch a real database - `conftest.py` blanks `MONGODB_URI`, so a
test that reaches an unstubbed collection fails loudly. The deploy workflows
run the suite before deploying, so a failing test stops the release.

## Curating

```bash
python -m scripts.show_suggestions        # places visitors suggested
python -m scripts.show_reports            # closed / wrong category / would go back
```

Both read the database named by `MONGODB_DB_NAME` (production by default in a
typical `.env`; prefix `MONGODB_DB_NAME=tlvbot_staging` to look at staging).

## Street-name data (typo suggestions)

`backend/data/streets.json` is the list of street names of Tel Aviv-Yafo, Ramat
Gan and Givatayim that `backend/services/streets.py` fuzzy-matches a mistyped
address against ("dizingof 50" -> "Did you mean Dizengoff 50?"). It is generated
from OpenStreetMap, so it is (c) OpenStreetMap contributors under the ODbL - the
attribution lives in the file's own `_meta` header and must stay there.

Regenerate it rarely (street names barely change):

    python -m scripts.build_street_index
