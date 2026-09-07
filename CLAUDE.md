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
- "Show more" pagination beyond the top 3 results - `/api/chat` now echoes
  back the matched `category` (null for "surprise me"), which the frontend
  stashes on the results entry and replays to a new `/api/more-places`
  endpoint with an increasing `offset`, so a repeat click fetches the next
  page of the same query without re-running the LLM categorization (cheap:
  no Anthropic call, just Mongo + OSRM). `db.find_nearest`/`build_geo_pipeline`
  gained an `offset` param that adds a `$skip` stage after `$geoNear`. The
  button hides itself once a page comes back shorter than the page size.
  Verified live against the real DB through several consecutive clicks
  (3 -> 6 -> 9 -> 12 -> 15 coffee spots), correctly sorted, no duplicates.
- PWA support - a web app manifest (`frontend/public/manifest.webmanifest`)
  plus hand-generated icons (`frontend/public/icons/`: 192/512 for
  Android/manifest, a separate opaque 180px one for `apple-touch-icon` since
  iOS renders transparent pixels there as solid black) make the app
  installable to a home screen with its own icon, name, and standalone
  (no browser chrome) display mode. No image tool was available on this
  machine (no Pillow, no ImageMagick/rsvg) - the icons are generated by a
  small pure-stdlib script (`zlib`/`struct`, hand-rolled PNG encoding) kept
  out of the repo (one-off, not part of the app). Also added a deliberately
  no-op service worker (`public/sw.js`, registered in `main.tsx`) purely to
  satisfy Chrome/Android's installability check for a registered SW with a
  fetch handler - it does no caching on purpose, since the app already gets
  correct freshness from `cache_control` middleware in `backend/app.py`
  (index.html always revalidated, hashed assets cached forever), and a
  caching SW would risk serving stale content after a deploy. It's served
  from `/sw.js` at the true root via a dedicated FastAPI route (not
  `/static/sw.js`) - a service worker's default scope is its own script's
  directory, and Chrome requires that scope to cover the manifest's
  `start_url` ("/") to consider the app installable.
  Verified live: manifest and both icon sizes resolve and fetch correctly
  (relative icon paths in the manifest resolve against the manifest's own
  URL, `/static/manifest.webmanifest`, which is what actually makes them
  land on `/static/icons/...`). Service worker registration couldn't be
  verified in this session's sandboxed browser preview (a generic error
  there looked like a proxy quirk in the local preview tunnel, not an app
  bug - a plain fetch of the same URL worked fine) - confirmed after
  deploying to the real Azure URL: "Add to Home Screen" on a real phone
  correctly installs it as a standalone app with its own icon.
- Help button/command - a `CircleHelp` icon button in the header (works
  even before location is set, since it also explains the location
  fallback), plus typing "help" as a chat message. Both handled entirely
  client-side (`App.tsx`'s `showHelp`) - no `/api/chat` call, so no LLM
  cost - and only hit the existing `/api/categories` endpoint to append a
  live, always-current category list rather than hardcoding one that would
  drift from the real data. Verified live both ways (button, and typing
  "help") - confirmed only `/api/categories` fires, never `/api/chat`.
- Light usage stats - two new collections, written from inside `/api/chat`
  (`backend/db.py`'s `record_category_request`/`log_unmatched_query`): a
  `category_stats` demand counter (`$inc` per category, plus
  `ANY_CATEGORY_KEY`/`UNMATCHED_KEY` buckets for "surprise me" and "nothing
  matched"), and an `unmatched_queries` log of the raw text whenever the LLM
  can't match anything - the actually useful part for curation, since it
  shows what people want that the map doesn't have yet. `unmatched_queries`
  has a TTL index (90 days) so it can't grow the free-tier database
  unbounded. Deliberately no new endpoint or UI - read both collections
  directly in Atlas (Compass or the web UI) when curious; not worth
  building and securing an API route for a personal curation tool. Verified
  live against the real DB (one matched "coffee" request, one nonsense
  query) - counters and the log entry landed correctly, then cleaned up
  since this was verification data, not real usage.
- Visual adjustments: help text split into several short bubbles instead of
  one block (readability); full Hebrew UI option; manual light/dark toggle.
  - **Help readability**: `App.tsx`'s help flow now pushes 4-5 short bubbles
    (intro+craving, surprise+results, mode+location, "type help again",
    plus the live categories line) instead of one big block.
  - **Hebrew (full bilingual, not just UI chrome)**: a `Languages`-icon
    toggle in the header flips `lang` between `en`/`he`, persisted in
    localStorage (`frontend/src/preferences.ts`) and applied as
    `document.documentElement.lang`/`dir` - `dir="rtl"` mirrors the whole
    layout for free since the CSS already used logical flex alignment
    (`align-self: flex-start/end`) everywhere except two chat-bubble corner
    radii, which were switched from physical (`border-bottom-left/right-
    radius`) to logical (`border-end-start/end-radius`) so the bubble
    "tail" stays on the correct side under RTL too. All UI strings live in
    `frontend/src/i18n.ts` (a plain `Record<Lang, Record<key,string>>`, no
    i18n library - the string set is small and fixed). `/api/chat` takes a
    `lang` field; `backend/app.py`'s `REPLIES` dict supplies the Hebrew
    reply templates, and `services/llm.py` tells Claude to write its
    `clarifying_question` in the requested language. Category names
    themselves (from the DB) are deliberately left untranslated even in
    Hebrew replies/help text - a maintained EN->HE category mapping would
    go stale exactly like the help command's live category list was built
    to avoid. Each `ChatBubble` (and place-card name) gets `dir="auto"` so
    a message's own text decides its alignment independent of the page's
    current direction - old English messages don't flip to right-aligned
    just because the UI language was switched to Hebrew afterward, and
    vice versa. Typing "help" or "עזרה" both trigger the local help flow
    regardless of current UI language. Verified live end-to-end: toggling
    language mirrors the whole layout correctly, a Hebrew query ("קפה")
    round-trips through the real LLM and gets a real Hebrew reply
    ("הנה המקומות הכי קרובים מסוג coffee:"), and switching back to English
    un-mirrors cleanly.
  - **Light/dark toggle**: a `Sun`/`Moon` header button flips `theme`
    between `light`/`dark`, persisted the same way; defaults to the OS
    preference (`prefers-color-scheme`) the first time, same as before,
    but now an explicit choice always wins over it in both directions
    (`theme.css`'s `:root:not([data-theme='light'])` under the dark media
    query, plus an unconditional `:root[data-theme='dark']` block).
- Conversational refinement / short-lived session memory - a follow-up like
  "something else", "another one", or "what else do you have" now continues
  the previous request instead of being treated as its own independent
  query. Deliberately NOT a server-side session: the frontend
  (`App.tsx`'s `getPreviousContext`) just looks at the most recent
  `places`-kind entry already in the chat log for its category and how many
  results have been shown, and sends that along on the next `/api/chat`
  call (`previous_category`, `previous_offset`, `has_previous_context`) -
  gone on reload, exactly the "short-lived" scope this was meant to have,
  with zero new storage/infra.
  `services/llm.py`'s tool schema gained an `is_followup` field, and the
  system prompt tells Claude what the previous turn's category was so it
  can judge whether this message is a refinement of that vs. a distinct
  new craving. When it's a refinement, `backend/app.py`'s `/api/chat`
  reuses the *same pagination mechanism built for "Show more"* - it just
  fetches the next page for the previous category starting at
  `previous_offset`, rather than resetting to the top 3 - so "something
  else" naturally surfaces places the user hasn't already seen. A new
  `no_more_matches` reply covers the case where that pagination is
  exhausted. The chat response now always includes an `offset` field
  (previously only `/api/more-places` needed one) so the frontend can pass
  the right number forward on the *next* turn too.
  One real bug caught and fixed via live testing against the real LLM (not
  just mocks): Claude doesn't reliably self-correct `is_followup` to false
  when it also extracts an explicit new category - "actually, pizza" right
  after a "coffee" context came back as `is_followup: true` *and*
  `matched_category: "pizza"` simultaneously, which would have silently
  kept serving coffee. Fixed with a deterministic override in
  `parse_food_request`: since `matched_category` only ever comes from the
  known category list (never freeform), a non-null category that differs
  from `previous_category` is treated as decisive proof of a new request,
  regardless of what `is_followup` says - prompt wording alone wasn't
  trustworthy enough on its own. Verified live end-to-end through the real
  UI: "coffee" -> "what else do you have" (served 3 different, previously
  unseen coffee spots) -> "actually, pizza" (correctly switched category
  rather than continuing coffee pagination).
- Kosher/dietary tags and filtering - tags are free-form hashtags typed
  into a pin's My Maps description (e.g. "#kosher #vegan"), the same field
  that already holds Instagram links - a deliberate choice (offered as a
  question, not assumed) over dedicating new My Maps layers to it, since
  layers are already spent on categories (~10-layer cap) and a place often
  needs more than one tag at once. `backend/parser.py` extracts them
  (`_TAG_RE`, lowercased/deduped, same file as the existing Instagram-link
  regex); `Place.dietary_tags: list[str]` is the new model field;
  `scripts/sync_places.py` refreshes it on every sync (unlike
  `instagram_url`, which intentionally never overwrites on update to
  preserve a manually-backfilled value - dietary tags have no such
  backfill path, so always-refresh is correct here, not a copy-paste of
  that behavior). `db.get_dietary_tags()` mirrors `get_categories()`
  (same caching, and `distinct()` on an array field auto-flattens to
  unique scalar values with no special handling needed) so the LLM always
  sees the real, current set of tags rather than a hardcoded one.
  `services/llm.py`'s tool schema gained `matched_dietary_tag`, extracted
  as its own dimension alongside category (e.g. "vegan burger" ->
  category=burger, tag=vegan; "anything kosher" -> any_category=true,
  tag=kosher) and reuses the exact same deterministic is_followup override
  already built for category (an explicit tag differing from the previous
  one always overrides a followup, for the identical reason). Filtering
  itself is a one-line Mongo addition (`{"dietary_tags": tag}` matches an
  array field against a scalar automatically) threaded through
  `find_nearest`/`build_geo_pipeline`, `/api/more-places`, and the
  conversational-refinement previous-context plumbing so "Show more" and
  "something else" both keep respecting an active tag filter instead of
  silently dropping it. Reply text and the "no matches"/"no more matches"
  messages all gained tag-aware variants (e.g. "Here are the closest vegan
  coffee spots:") so the constraint is never silently ignored in the
  bot's own words either. Place cards show each result's tags as chips
  next to the category chip. Verified live end-to-end against the real DB
  and LLM: temporarily tagged a real place (Jera) as vegan, confirmed
  "vegan coffee" correctly filtered to just that one place with the right
  reply text and tag chip, confirmed a plain "coffee" query was unaffected
  (still returned all coffee spots), confirmed a followup after
  exhausting the one vegan result replied "That's all the vegan coffee
  spots I have saved for now." rather than silently dropping the tag -
  then reverted the temporary tag.

### Deferred (explicitly, revisit later)
- Public transit ETA — needs Google Distance Matrix (real cost/setup
  tradeoff vs. the free OSRM walk/drive ETAs already in place)

### Scoped, not yet built (priority order)
1. ~~Rate limiting on `/api/chat`~~ - done, see above.
2. ~~Improved icons~~ - done, see above.
3. ~~WhatsApp export/share button~~ - done, see above.
4. ~~Plan-ahead / typed-address geocoding~~ - done, see above.
5. ~~Scheduled auto-sync~~ - done, see above.
6. ~~"Show more" pagination beyond the top 3 results~~ - done, see above.
7. ~~PWA support~~ - done, see above.
8. ~~Light usage stats~~ - done, see above.
9. ~~Conversational refinement / short-lived session memory~~ - done, see
   above.
10. ~~Kosher/dietary tags and filtering~~ - done, see above.
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
