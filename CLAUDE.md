# TLV Bot

## What this is

A recommendation chatbot for Tel Aviv food and coffee spots. You tell it what
you're craving and where you are, and it finds the closest match from a
curated Google My Maps list — with distance, a real walking/driving ETA, a
one-tap navigation link, and an Instagram link where available.

## Why it exists

This is a computer science graduate's side project, born out of years of
personally collecting favorite food and coffee spots around Tel Aviv into a
Google My Maps list. The goal is to turn that personal list into something
genuinely useful — first for the creator, then for friends and family, and
potentially into a real small product down the line. It's a real, running
project with real (if modest) usage, not a toy or a tutorial exercise.

## Goals

- **Personal utility first.** It should be the fastest way to answer "what's
  good and close by right now" using a list the creator actually trusts,
  rather than sifting through generic reviews.
- **Grow to friends and family**, then possibly beyond. Every architectural
  decision (auth, data model, hosting) is made with this trajectory in mind —
  not over-built for a hypothetical scale, but not so disposable it needs a
  rewrite the moment a second real user shows up.
- **Stay cheap, deliberately.** Hosting/DB/API costs are capped at **$12/month**
  even though there's a $100 Azure credit (GitHub Student pack) available —
  the credit is a cushion, not a budget. In practice this runs at roughly
  $1-2/month by leaning on free tiers (MongoDB Atlas M0, Azure App Service
  F1, free public OSRM routing) and a cheap, fast LLM (Claude Haiku 4.5) for
  the one paid dependency. Any new feature or dependency should be evaluated
  against this constraint, not just "does it work."
- **Keep the data source easy to maintain.** The place list is curated by
  hand in Google My Maps (the format the creator already uses day to day) -
  the app syncs from it, not the other way around.

## Architecture (current)

- **Backend:** FastAPI (Python 3.11), in `backend/` — `app.py` (routes),
  `db.py` (MongoDB access), `models.py` (Pydantic schema, single source of
  truth for a place document), `parser.py` (KML parsing), and
  `services/` (one module per external integration: `llm.py` for Claude NLU,
  `routing.py` for OSRM ETAs, `location.py` for Google Maps link resolution).
- **Frontend:** React + TypeScript, in `frontend/`, built with Vite straight
  into `static/` for FastAPI to serve.
- **Database:** MongoDB Atlas, free M0 tier. Places are matched by physical
  proximity (not name) so renaming a pin on the map doesn't look like a
  delete+recreate. A `$jsonSchema` validator runs in `warn` mode as
  defense-in-depth alongside the Pydantic models.
- **NLU:** Claude Haiku 4.5, one tool-call per chat message to match
  free text to a known category.
- **Routing:** free public OSRM instances (routing.openstreetmap.de) for
  real walking/driving ETAs - no API key, no billing.
- **Hosting:** Azure App Service, Free (F1) tier. Deployed via GitHub Actions
  on every push to `main` (builds the frontend, then the Python app).
- **Data source:** a Google My Maps custom map, shared publicly, synced via
  `scripts/sync_places.py`.

See `README.md` for setup/run instructions and the full directory structure.

## To-do list

### Done since the priority ordering
- Rate limiting on `/api/chat` (`slowapi`, per-IP, 20/minute + 200/day) -
  protects the budget goal against abuse/automated hammering. In-memory
  (single App Service instance, no shared store needed). Tests disable it
  via an autouse `conftest.py` fixture (`TestClient` requests all share one
  fake IP, so without this the limit would accumulate across the whole test
  session instead of resetting per test).
- Improved icons - swapped the plain emoji (📍🚶🚗🗺️📱) for `lucide-react`
  (tree-shakeable, `currentColor`-based so it auto-adapts to both themes).
  Note: lucide-react dropped brand/logo icons (trademark reasons), so the
  Instagram link uses `Camera` rather than a literal Instagram glyph.
- Also fixed in passing: the manual location input had no styling at all
  (just `flex:1`, no padding/border/sizing) and rendered as a tiny,
  hard-to-tap box; the location-request flow now reads as an actual
  two-turn conversation (explicit ask up front, a real follow-up chat
  message if permission doesn't come through) instead of one static line.
- WhatsApp export/share button (`ShareButton` on each results list) -
  formats the 3 places into shareable text, prefers the native Web Share
  API (best UX, WhatsApp included among the options on mobile), falls back
  to a real `<a href="https://wa.me/...">` link where that API isn't
  available. Deliberately a real anchor, not an imperative `window.open()`
  - confirmed live that `window.open()` from script gets popup-blocked in
  some browser contexts, while a genuine anchor click is always trusted
  navigation.
- Fixed a real mobile bug: if location permission was denied/off at first
  load and then enabled afterward (e.g. in phone settings), nothing in the
  app noticed - it required a full page reload to pick up. Added a "Try
  enabling location again" button that re-attempts geolocation on demand;
  a repeated failure updates the status line rather than spamming another
  chat bubble each time.
- Plan-ahead / typed-address geocoding (`services/location.geocode_address`,
  free via Nominatim, no key/billing) - `/api/resolve-location` now tries
  Maps-link extraction first, then falls back to geocoding the text as a
  free-form address/landmark. Deliberately appends "Tel Aviv-Yafo" (the
  official municipality name) to every query: verified live that a bare
  city-less or "Tel Aviv"-only query is genuinely ambiguous in Israel (e.g.
  "Rothschild 12" alone resolved to a same-named street in Holon, not the
  actual Rothschild Blvd) - the full official name disambiguates reliably
  without restricting results to a hard bounding box.
- Scheduled auto-sync (`.github/workflows/sync_places.yml`) - runs
  `scripts.sync_places` daily via GitHub Actions cron (4am UTC), plus a
  `workflow_dispatch` trigger for on-demand manual runs. Credentials
  (`MONGODB_URI`, `MONGODB_DB_NAME`, `MYMAPS_ID`) live in GitHub repo
  secrets, never in the workflow file. Verified live with a manual run
  against the real database - correctly parsed the live map and reconciled
  the DB (removed a place no longer on the map, landed at the right total).

### Deferred (explicitly, revisit later)
- Public transit ETA — needs Google Distance Matrix (real cost/setup
  tradeoff vs. the free OSRM walk/drive ETAs already in place)

### Scoped, not yet built (priority order)
1. ~~Rate limiting on `/api/chat`~~ - done, see above.
2. ~~Improved icons~~ - done, see above.
3. ~~WhatsApp export/share button~~ - done, see above.
4. ~~Plan-ahead / typed-address geocoding~~ - done, see above.
5. ~~Scheduled auto-sync~~ - done, see above.
6. "Show more" pagination beyond the top 3 results - small extension of
   the existing nearest-match query.
7. PWA support (add-to-home-screen, app-like icon) - builds directly on
   the icons from #2.
8. Light usage stats - category-level demand counters + a log of unmatched
   queries, to inform which categories to add/refine/drop (My Maps caps
   out around 10 layers, so this matters for curation decisions). Real
   value, but not an urgent decision yet.
9. Conversational refinement / short-lived session memory (so "something
   cheaper" or "further is fine" can build on the last answer instead of
   every message being stateless) - meaningfully bigger than anything
   above it (new state, prompt changes).
10. Kosher/dietary tags and filtering (locally relevant for Tel Aviv) -
    needs a data-model change (tag places) plus LLM/query changes.
11. Shorten/change the Azure URL (custom domain, or rename the App
    Service) - lowest urgency, purely cosmetic, and needs a decision
    (buy a domain vs. just live with a renamed App Service) before it's
    even scoped.

### Visual upgrades
- Map view - a visible map showing the recommended place(s), on top of the
  existing chat/list view (the original "chat now, map later" plan from
  early in the project). (Improved icons moved into the priority list
  above, at #2.)

### Bigger builds - user system (sequenced, not started)
Goal: real accounts usable by friends and family now, with an eye toward a
full product later.
1. Auth core - **Google Sign-In (OAuth)** as the actual front door, not
   self-managed passwords - delegates credential security (storage, breach
   detection, reset flows) entirely to Google, which is the right call for a
   personal project two-plus people are trusting with their data. Paired
   with the app's own short-lived JWT access/refresh session layer
   (matching prior hands-on experience from a university project), issued
   after verifying the Google ID token once: access token in memory (not
   localStorage), refresh token in an `httpOnly`/`Secure`/`SameSite=Strict`
   cookie, revocable (a stored token version/hash per user). Testing doesn't
   need real OAuth - mint a JWT directly for a test user in test setup, since
   what's being tested is "does the app handle this token correctly," not
   "does Google's login page work."
2. Favorites (save spots from the list)
3. Ratings
4. User-suggested new places, with a moderation queue (never auto-publish
   user input to the shared list) - simpler than map uploads, so it comes
   first
5. User map uploads + switching between multiple maps/datasets - needs the
   KML parser hardened first (`defusedxml`, size caps, per-user namespacing,
   since `xml.etree.ElementTree` is vulnerable to entity-expansion attacks on
   untrusted input)

One flagged tradeoff: growing past personal/occasional friends-and-family
traffic will eventually outgrow the Azure App Service Free (F1) tier's
60 CPU-minutes/day cap - the next tier up (~$13/month) alone would just
about break the $12/month budget. Not a problem yet: worth watching.
