# 📍 TLV Bot

A web chatbot that recommends the closest spot from your own curated Google My Maps
map of favorite Tel Aviv food places. Tell it what you're craving, share your
location, and it finds the nearest match with a one-tap navigation link.

This started as a WhatsApp bot (Twilio + Azure PostGIS Postgres); it's now a
lightweight web app so it can run for well under $12/month.

## ✨ Features

* **Free-text cravings:** "ramen", "something with meat", "coffee near here" -
  Claude (Haiku 4.5) matches your message to a category from your map.
* **Nearest-match search:** MongoDB's geospatial `$geoNear` finds the 3 closest
  places in that category to wherever your browser says you are.
* **One-tap navigation:** every result includes a Google Maps directions link
  (no Google Maps API key or billing needed - it's a plain deep link).
* **Auto-updating database:** re-run one script to pull the latest pins straight
  from your public Google My Maps map - no manual export/import step. Edits to
  `instagram_url` (or anything else you add by hand in MongoDB Atlas) are
  preserved across syncs.

## 🏗️ Architecture

* **Frontend:** React + TypeScript (`frontend/`), built with Vite straight into
  `static/` (content-hashed filenames, cached forever; `index.html` itself is
  always revalidated so it picks up the latest build). Uses the browser
  Geolocation API, with a manual lat/lon or Google Maps link fallback.
* **Backend:** FastAPI (Python 3.11), serving both the built page and a
  `/api/chat` JSON endpoint.
* **Database:** MongoDB Atlas, free-forever M0 tier (512MB). A `2dsphere` index
  on each place's location powers the nearest-match queries.
* **NLU:** Anthropic API, `claude-haiku-4-5` - one small tool-call per chat
  message to match free text to a known category. At personal-project volume
  this runs about $1-2/month.
* **Hosting:** Azure App Service, Free (F1) tier - $0/month, deployed via the
  existing GitHub Actions workflow in `.github/workflows/`.
* **Data source:** a Google My Maps custom map, shared publicly, exported as
  KML on demand via its stable `mid=` URL.

Total running cost at personal-project scale: well under $1/month typically,
comfortably inside a $12/month budget with room to spare.

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
```

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
uvicorn app:app --reload
```

Open `http://localhost:8000`.

### 9. Deploy

`.github/workflows/main_nadav-tlv-bot.yml` builds the frontend (Node) and then
the Python app, on every push to `main` - no manual steps needed there. Just
make sure the four env vars above are set in the App Service's Configuration ->
Application settings, and set the startup command to:

```
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

## Structure

```
app.py, db.py, llm.py, location.py,   FastAPI app + its modules. Kept at
  parser.py, routing.py, models.py      repo root - Azure's startup command
                                         and Oryx's build both target this
                                         layout directly; moving it means
                                         updating the Azure Portal too.
                                         models.py is the schema (Pydantic) -
                                         single source of truth for what a
                                         place document looks like.
scripts/                                Maintenance CLI scripts, run as
  sync_places.py                          python -m scripts.sync_places
  seed_instagram_from_csv.py              python -m scripts.seed_instagram_from_csv
data/                                   Local data files (gitignored - your
  map.kml, cleaned_places.csv             curated list stays private)
frontend/                               React + TypeScript chat UI (source)
static/                                 Generated by frontend's build -
                                         gitignored, don't edit by hand
tests/                                  pytest suite - conftest.py at the
                                         root adds it to sys.path
```

## Running tests

```bash
pytest
```
