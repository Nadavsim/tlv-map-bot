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
- **Stay cheap, deliberately.** Hosting/DB/API costs are capped at **$15/month**
  (raised 2026-09-10 from the original $12 specifically to afford a dedicated
  Azure App Service plan for production — see "Production/staging environment
  split" below for why the Free tier alone stopped being viable) even though
  there's a $100 Azure credit (GitHub Student pack) available — the credit is
  a cushion, not a budget. In practice this runs at roughly $14-15/month:
  production's Basic (B1) App Service plan (~$14.45/month) is the one real
  line item; everything else is still free (MongoDB Atlas M0 hosts both the
  production and staging databases at no extra cost, staging's own App
  Service stays on the Free F1 tier, OSRM routing is free) or the one other
  paid dependency, a cheap fast LLM (Claude Haiku 4.5, a few dollars/month at
  personal-project volume). Any new feature or dependency should be evaluated
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
- **Database:** MongoDB Atlas, free M0 tier, one cluster hosting two
  databases — `tlvbot` (production, real data) and `tlvbot_staging`
  (staging, an isolated copy, not auto-synced — see below). Places are
  matched by physical proximity (not name) so renaming a pin on the map
  doesn't look like a delete+recreate. A `$jsonSchema` validator runs in
  `warn` mode as defense-in-depth alongside the Pydantic models.
- **NLU:** Claude Haiku 4.5, one tool-call per chat message to match
  free text to a known category.
- **Routing:** free public OSRM instances (routing.openstreetmap.de) for
  real walking/driving ETAs - no API key, no billing.
- **Hosting:** Azure App Service, split into two environments (see
  "Production/staging environment split" under Done below for the full
  story of why and the gotchas hit setting it up):
  - **Production** — App Service `Nadavbot-TLV`, Basic (B1) tier, its own
    dedicated App Service Plan (`nadav-bot-plan`) and resource group
    (`tlv-bot-prod-rg`). Deploys via `.github/workflows/deploy-production.yml`
    on every push to `main`.
  - **Staging** — App Service `nadav-tlv-bot` (the original app, repurposed),
    Free (F1) tier, its own App Service Plan, resource group `tlv-bot-rg`.
    Deploys via `.github/workflows/deploy-staging.yml` on every push to a
    `staging` branch. Points at the `tlvbot_staging` database.
  - Both currently sit on Azure's auto-generated hostnames (e.g.
    `nadavbot-tlv-<random>.israelcentral-01.azurewebsites.net` - Azure
    appends a random suffix + region to new App Service default hostnames
    for global-uniqueness reasons, so this isn't fixable by renaming). A
    custom domain was considered and explicitly deferred - see the Roadmap.
- **Data source:** a Google My Maps custom map, shared publicly, synced via
  `scripts/sync_places.py`. The scheduled sync workflow only updates
  production; staging's data is a one-time seed, manually re-run when
  wanted (`MONGODB_DB_NAME=tlvbot_staging python -m scripts.sync_places`).

See `README.md` for setup/run instructions and the full directory structure.

## Roadmap (revised 2026-09-24 - organized by theme and horizon)

Restructured from a flat, numbered priority list into the shape a real
product team uses - by **theme** (what problem it serves) and **horizon**
(Now / Next / Later, not fake dates), following a three-perspective review
(Customer, R&D, Marketing, run independently and blind to each other)
reconciled by a product-management pass. Full source material: "The
Trusted List" (the raw three-perspective review) and "Next Stops" (the
same material as a Now/Next/Later board) - both are session artifacts, not
committed to the repo, since they're planning documents rather than app
code. The old items 1-7 below are superseded by this structure; everything
in them that shipped is still true and is summarized in "Already shipped"
below.

**Prioritization principle:** ordered by leverage-per-hour, not feature
size or a release calendar - the real constraint is one maintainer's spare
time, not money or a deadline, so cheap-and-certain beats big-and-
speculative every time.

**Standing guardrail (from the Marketing review):** deliberately hold off
on any public or group-chat distribution push - no invite mechanics, no
landing page optimized for strangers. At this stage the thing being
protected is trust depth in a small, known cohort; trading that for
breadth is a real cost, not a free win, and none of the items below
change that call.

**Already shipped** (context, not a to-do - full history in "Done since
the priority ordering" below): custom domain explicitly declined, a full
Impeccable design pass (score 31 -> 36/40), privacy policy/404/error
boundary/robots.txt, the production/staging environment split, manual-
location mode, and auth core (Google Sign-In + JWT sessions with the
slide-out account menu) - built, verified live, and in production as of
2026-09-13.

**Now** (ready to start, no open decisions, mostly $0):
- **Trust** - put "one trusted list, not reviews" into the product's own
  copy: the chat greeting, the WhatsApp share text, help text, OG tags.
  The single most agreed-upon idea across all three reviews - the story
  is already true, it's just never told where a first-time user sees it.
- **Trust** - hours + weather hashtags (`#until23`, `#breakfast`,
  `#indoor`), reusing the exact `#kosher`/`#$$$` pattern already proven.
  The cheapest way to stop recommending a place that's actually closed.
- **Reliability** - a `/health` endpoint wired into Azure B1's built-in
  health check, plus free uptime and error alerts. This app has already
  failed silently once, mid-project, with nobody alerted.
- **Reliability** - swap `parser.py`'s XML parsing to `defusedxml` now,
  ahead of any user-uploaded map.
- **Growth** - fire the PWA install prompt right after a shared link's
  first good result, not on generic first load.

**Next** (queued - mostly build on something in Now, or need one small
call):
- **Usability** - let free text set price/occasion ("something cheap," "a
  date spot") onto the `price_tier` field that already exists.
- **Usability** - a one-time guided first message for a brand-new
  session, reusing the Help flow's own chat-bubble pattern.
- **Usability** - saved/frequent manual address, tied to the account that
  just shipped. Privacy constraint carries forward unchanged: no semantic
  labels like "Home"/"Work" (see the original note below).
- **Reliability** - cache + graceful degradation around OSRM/Nominatim,
  before real concurrent friend-group traffic trips their usage limits.
- **Reliability** - lock the Favorites schema now: a dedicated
  `{user_id, place_id}` collection with a compound unique index, not an
  array on the user document - free to decide now, expensive to fix
  under real data later.
- **Growth** - make "I added the place you asked about" a standing habit
  when curating - the one growth move no competitor at any size can copy.
- **Intelligence** - a weekly, manual-trigger LLM pass over
  `unmatched_queries` proposing new categories/tags.
- **Trust** - "this place closed / wrong category" feedback action - now
  explicitly the second line of defense behind hours-tagging above, not
  the primary one.
- **Usability** - Favorites (save a spot for later), once the schema
  above is locked in.
- **Trust** - a private "I'd go back" signal, visible only to the
  curator - the user's explicit 2026-09-24 call on the open "Ratings"
  question this review raised: not public star ratings (risks the
  product's whole "curated, not crowdsourced" identity - a friend
  circle's one-star drive-by would carry outsized weight against the
  curator's own pick, with no volume to average it out), but a private
  signal that feeds curation the same way the closed-place feedback
  action does, without ever becoming a crowd signal shown to other users.
  Not blocked on anything, so pulled forward into Next once the call was
  made.

**Later** (needs a real decision first, or is a bigger technical bet):
- **Usability** - two-person / meet-in-the-middle search, reusing the
  existing manual-location geocoding almost entirely.
- **Usability** - map view: plot the set location and the recommended
  spot(s) together, on top of the existing chat/list view. Leaflet + free
  OpenStreetMap tiles, matching the OSRM/Nominatim pattern already in
  place rather than a paid Maps API.
- **Intelligence** - semantic search over place descriptions:
  precomputed embeddings, in-process cosine similarity. Deliberately
  **not** MongoDB Atlas Vector Search, which alone needs an M10+ cluster
  - roughly 4x the entire monthly budget.
- **Growth** - a static About/story page, same cost pattern as the
  existing privacy/404 pages.
- **Reliability** - decide on purpose whether sign-out should revoke
  every device or just one (currently: every device, via
  `token_version`) - before Favorites makes staying signed in matter.
- **Usability** - session-local "don't suggest what I already navigated
  to" - may end up folded into Favorites instead of built separately.
- **Trust** - user-suggested new places, with a moderation queue (never
  auto-publish user input to the shared list) - carried over unchanged
  from the original roadmap; not part of the three-perspective review's
  scope, so it wasn't independently re-examined the way Ratings and
  multi-curator uploads were. Complements the informal "I added the place
  you asked about" follow-up habit in Next with a real submission flow,
  once that outgrows a few close friends.

Also still open, carried over unchanged from "Visual upgrades" below:
category icons on the result chips, and generating a formal `DESIGN.md`.
Neither was in scope for the three-perspective review, so they're not yet
placed on a horizon - revisit alongside whichever theme they end up
serving. (The map view itself was added to the Later horizon above,
2026-09-24, at the user's explicit request.)

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
    to avoid. Each `ChatBubble` gets `dir="auto"` so a message's own text
    decides its alignment independent of the page's current direction -
    old English messages don't flip to right-aligned just because the UI
    language was switched to Hebrew afterward, and vice versa.
    Place-card names deliberately do NOT get this treatment (see the
    "Production/staging environment split" era's RTL fixes below for why -
    short version: per-name `dir="auto"` was tried and reverted twice,
    since it either misaligns a name against its own card's chips/buttons,
    or - if applied to the whole card - makes cards in the same list flip
    layout differently depending on each name's own script. Uniform,
    page-language-consistent card layout was chosen over per-name
    correctness, confirmed again in the 2026-09-10 fourth critique re-run
    when this exact gap was flagged and the user re-confirmed the
    trade-off rather than re-litigating it). Typing "help" or "עזרה" both
    trigger the local help flow regardless of current UI language.
    Verified live end-to-end: toggling
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
- Production/staging environment split (2026-09-10) - see the Hosting
  entry under Architecture above for the resulting shape. Done ahead of
  auth work specifically, since real sessions/accounts are exactly the
  kind of thing that shouldn't be debugged against production. The path
  to get there was rockier than expected and worth remembering:
  - **A new App Service was created for production** (`Nadavbot-TLV`) so
    the *old* app (`nadav-tlv-bot`) could be repurposed as staging rather
    than standing up a third app - reused its existing GitHub secret and
    avoided an unnecessary Azure rename (Azure doesn't support in-place
    App Service renames anyway - the "new app, old app becomes staging"
    approach sidesteps that entirely).
  - **Azure for Students allows only one Free-tier App Service Plan per
    region per subscription.** Creating a second Free plan for the new app
    hit a quota error immediately - had to share `nadav-tlv-bot`'s existing
    plan at first.
  - **Sharing a plan between production and staging is actively dangerous,
    not just inelegant** - proven live, not hypothetical: this session's
    own deploy/restart churn on the shared plan burned through the Free
    tier's 60 CPU-minutes/day cap and took the real production app down
    for actual users, right in the middle of setting up the thing meant to
    prevent exactly that. Directly motivated paying for Basic (B1) on
    production instead of continuing to share.
  - **You cannot migrate an App Service to a plan in a different resource
    group** ("Cannot change the site ... due to hosting constraints" is
    Azure's error for this, confirmed via the Activity Log - a generic
    message that also gets thrown for a couple of unrelated conditions, so
    don't assume it always means this). The Portal's own "Change App
    Service plan" dialog doesn't support attaching to a plan by name either
    - it only creates new ones. Once a plan is created in the right
    resource group up front, this whole class of problem disappears - the
    working fix here was deleting and recreating the App Service directly
    in the target resource group with the existing plan selected at
    creation time, rather than trying to migrate an existing app into place.
  - **A manually-created App Service doesn't get `SCM_DO_BUILD_DURING_
    DEPLOYMENT=true` automatically** - only Azure's own "set up CI/CD from
    the Portal" wizard adds that app setting for you. Without it, Oryx
    never runs `pip install` server-side, so the deployed app has no
    dependencies at all (`No module named uvicorn` in the Log stream, not
    a crash or a timeout - a genuinely different symptom worth recognizing
    quickly rather than assuming it's just still cold-starting). Any App
    Service created by hand needs this setting added explicitly.
  - Custom domain purchase (originally item 1 on the Roadmap below) was
    explicitly declined once it became clear the Basic-tier upgrade could
    stand alone - a clean URL was judged purely cosmetic against getting a
    working prod/staging split, so the app stays on Azure's own
    auto-generated hostnames for now (see the Hosting entry above for why
    those aren't easily prettied up either way).
- Manual-location as a real mode (2026-09-11) - previously, the typed-
  address/Maps-link/coordinates path only ever appeared as a fallback
  when live geolocation failed; there was no way to plan ahead for a
  different address while live location was working fine. Added a
  Live/Custom toggle (`Header.tsx`, styled identically to Walk/Drive):
  - `App.tsx` tracks `liveLocation` and `manualLocation` as separate
    state (previously one `userLocation`), plus `manualLocationLabel` (the
    raw text the user typed, echoed back verbatim - not translated, same
    reasoning as place names) and a `locationMode: 'live' | 'manual'`
    flag. `activeLocation` (whichever the mode points at) is what
    actually gets sent to `/api/chat`/`/api/more-places` - no backend
    changes needed, since both endpoints already just take `lat`/`lon`.
  - **Custom is the default**, not Live - live geolocation is never
    requested automatically on load; the address form just starts open.
    Clicking **Live** is what triggers the browser's permission prompt,
    reusing the last known fix instantly if one already exists. Clicking
    **Custom** reactivates the last-used manual location instantly if one
    exists, otherwise opens the address form. A "Change" link next to the
    status line is the way to update an already-active manual location.
  - The first version of this shipped with the opposite default (Live
    first, matching the old behavior) and two real bugs the user caught
    on a real device that this session's own sandboxed testing missed:
    (1) clicking a toggle option didn't visually highlight it if that
    branch's code path forgot to call `setLocationMode` before doing
    anything async - fixed by making `handleLocationModeChange` call
    `setLocationMode(newMode)` unconditionally and immediately, before
    any geolocation request, so the toggle always reflects the click
    instantly regardless of what happens next; (2) `LocationForm`'s "Try
    enabling location again" button/copy is unconditionally part of the
    form, so proactively choosing Custom mode (nothing had failed) showed
    error-flavored copy implying something had gone wrong. Both prompted
    the bigger redesign above (Custom-by-default) rather than patching
    the symptom - once Live only ever triggers a request in direct
    response to a click, there's no more "silent automatic attempt vs.
    explicit retry" distinction to get wrong, and the button's copy was
    reframed positively as "Use my current location" (`locationUseLiveButton`
    in `i18n.ts`) so it reads correctly in every context it can appear in,
    not just a failure. This also let a whole guard (`locationModeRef`,
    protecting a race that no longer exists once nothing calls
    `requestLocation` on mount) come back out.
  Verified live in both languages, both themes, desktop and mobile: fresh
  load shows Custom active by default with no location-denied chat bubble
  or error-flavored copy anywhere; clicking Live immediately highlights it
  and requests geolocation (denied in this sandbox, confirmed the status
  line updates without disabling chat or losing the active manual
  location); switching back to Custom instantly restores the manual
  location and its label with no re-typing; a real chat query against the
  manual location returned correct results; no mobile layout regression.
- Fixed two more real-device bugs in the manual-location toggle
  (2026-09-11), and a third design issue caught in the same pass:
  - **Custom mode still showed the "Use my current location" button**,
    and clicking it silently forced `locationMode` back to `'live'` -
    `requestLocation`'s success handler always sets `locationMode('live')`
    unconditionally, so a Custom session with no address typed yet would
    get hijacked into Live the moment that button succeeded, with no way
    back to the address form short of switching the toggle off and back
    on. Root cause: `LocationForm` mixed both modes' concerns in one
    component - the retry button (Live's job) and the address input
    (Custom's job) always rendered together, regardless of which mode was
    actually active. Fixed by giving it a `showLiveRetry` prop and
    rendering ONE OR THE OTHER, never both - Live mode only ever shows a
    "try again" button (asks the browser, never the user, for detail),
    Custom mode only ever shows the address form. This makes the bug
    structurally impossible now, not just patched: nothing in Custom
    mode's UI can call `requestLocation` anymore.
  - **The status message didn't match the active mode** - Custom mode's
    default state showed generic copy that didn't mention how to actually
    proceed. Reworded `locationNotSet` to "Insert a location below, or
    switch to Live." and `locationDenied` (Live's failure state) to
    "...try again, or switch to Custom" (previously said "use the box
    below," which no longer exists in Live mode's own view).
  - **Toggle button order didn't align with Walk/Drive** - Custom/Live
    was ordered to visually pair with Drive/Walk (the "off"/"on" halves
    landing on opposite sides between the two toggle rows) rather than
    Custom pairing with Walk. Reordered the JSX (Custom first, Live
    second) so Custom+Walk share one side and Live+Drive share the other,
    in both LTR and RTL.
  Verified live in both languages: fresh load shows only the address
  form with the reworded prompt; switching to Live shows only the retry
  button with the reworded failure copy; "Change" still reopens only the
  address form, never the retry button; a full Custom -> Live -> Custom
  round trip preserves the manual location and its label exactly as
  before; toggle alignment confirmed in the RTL screenshot (מותאם/הליכה
  share the right edge, נוכחי/נסיעה share the left).
- Real-device report (2026-09-11): tapping "Use my current location" a
  second time didn't show the browser's permission popup at all. First
  attempt assumed this always means a permanent, settings-only block, and
  shipped a `locationBlocked` status asserting exactly that whenever
  `GeolocationPositionError.code === PERMISSION_DENIED`. That shipped fix
  was itself wrong and got reverted the same day: researched actual
  browser behavior (Chrome persists an explicit "Block" tap as a site
  setting and stops re-prompting, but a mere dismissal only soft-blocks
  temporarily after repeated attempts; Safari's behavior is murkier still,
  and its Permissions API is independently known to misreport denied as
  `"prompt"`) and confirmed `PERMISSION_DENIED` (code 1) is the *same*
  code for a fresh, retriable denial, a persisted explicit block, and a
  couple of unrelated failure modes - client-side JS cannot tell them
  apart. Asserting "permanently blocked, go to settings" after a single
  failure was overclaiming, and actively wrong advice on a genuinely
  recoverable denial (it discourages a retry that might well have worked).
  Reverted to one honest, non-committal `locationDenied` message: "try
  again, or switch to Custom. Still stuck? Check this site's location
  permission in your browser settings" - the settings path is offered as
  a fallback, not asserted as the only option. `locationBlocked` and the
  `.code` branching were removed entirely rather than kept unused.
  Lesson for next time: don't infer permission *history* from a single
  browser API result that's documented to collapse multiple distinct
  causes into one code - verify the actual platform behavior before
  shipping a message that asserts something specific about it.
  Root cause finally confirmed the same day, diagnostically rather than
  by guessing again: asked the user two direct questions instead of
  shipping a third speculative fix - whether the status line updates at
  all on tap (it does, briefly, before showing the denied message - so
  the click genuinely reaches the geolocation call, ruling out a stuck
  `isRequestingLocation` or a dead click handler) and which browser
  (Android Chrome). That combination means this device's Chrome has
  Location genuinely set to Blocked for this specific origin - not a
  code bug at all, and not something any website's JS can override,
  by design. Chrome only shows the native prompt when the per-site
  permission is in its default "Ask" state; once a user (or Chrome's own
  repeated-dismissal auto-block) sets it to Blocked, every future
  `getCurrentPosition()` call fails immediately and silently, exactly as
  observed. The fix is entirely on the user's device (Chrome's per-site
  Location permission, reachable via the icon left of the address bar,
  or Settings -> Site settings -> Location -> the blocked-sites list) -
  no further app change was made, since the app already both correctly
  detects the denial and offers Custom mode as a fully working
  alternative in the meantime.
  That diagnosis was also wrong, disproven step by step the same day:
  enabling Android's system Location toggle (it had been off) didn't fix
  it; confirming Chrome's own OS-level app permission was already
  "Allow" didn't explain it; finding no entry at all in Chrome's
  per-site Blocked list ruled out an explicit block; a full "Delete &
  reset" of all Chrome-stored data for the exact origin (wiping any
  quieter, non-listed auto-mute state too) still didn't fix it;
  confirming the URL was genuinely `https://` ruled out the
  insecure-context explanation. Every plausible *permission*-shaped
  explanation was individually tested and eliminated - which was the
  signal to stop treating this as a permissions problem at all and
  actually read the code path again. The real bug: `requestLocation`'s
  failure callback took no error argument and collapsed all three
  distinct `GeolocationPositionError` codes - `PERMISSION_DENIED`,
  `POSITION_UNAVAILABLE`, and `TIMEOUT` - into one `locationDenied`
  message that always said "check your location permission," even
  though the latter two have nothing to do with permissions at all.
  Combined with `enableHighAccuracy: true` and only a 10s timeout - GPS
  routinely takes longer than that (or never gets a fix at all) indoors
  - a plain TIMEOUT was the likely real, everyday cause, misreported as
  a permissions issue on every single occurrence, sending the user
  through several rounds of device-settings troubleshooting that could
  never have fixed a GPS timeout. Fixed by reading `error.code` and
  branching into three honest, distinct messages (`locationDenied`,
  new `locationUnavailable`, new `locationTimeout`), and by switching to
  `enableHighAccuracy: false` with a more generous 20s timeout - this
  app only needs "which nearby place is closest," not GPS-grade
  precision, so the faster, more reliable network/wifi-based fix is the
  better trade-off and should make genuine timeouts rare going forward.
  Verified live by mocking `navigator.geolocation.getCurrentPosition` to
  return each of the three codes directly (can't force a real device
  into TIMEOUT/UNAVAILABLE from this sandbox) - each now produces its
  own distinct, accurate message in both languages, and the real
  (unmocked) denial in this sandbox still correctly resolves to
  `locationDenied` as before. Lesson for next time: when every
  individually-plausible cause in one category gets ruled out one by
  one, that is itself a strong signal to stop searching within that
  category and re-read the actual code path instead of reaching for
  another guess in the same direction.
  Still not resolved as of this same day - the timeout/high-accuracy fix
  above didn't fix it either. A screen recording of the actual failure
  (analyzed by extracting frames with `imageio`+bundled ffmpeg, since
  Claude Code has no native video support) showed the failure landing in
  well under a second - far too fast to be a real GPS/network location
  attempt or a human interacting with any permission UI, which is only
  consistent with the browser already holding a stored decision for this
  origin and refusing instantly without even trying. That re-opened the
  permission-blocking theory despite the user's own reset attempt not
  fixing it. Checked for a `Permissions-Policy` header/meta tag that
  could block geolocation at the page level regardless of user
  permission (would explain an instant failure with zero entry in
  Chrome's site list, since the page's own policy would pre-empt the
  permission system entirely) - not present anywhere in `backend/app.py`
  or `frontend/index.html`; also re-confirmed `public/sw.js` is still a
  genuine no-op (no caching, so not serving a stale cached bundle
  either). With every code-side explanation checked and none of them
  panning out, added a TEMPORARY diagnostic (`debugLocationError` state
  in `App.tsx`) that appends the raw `GeolocationPositionError.code` and
  `.message` directly onto the visible status line - deliberately
  user-visible rather than console-only, since the user's own phone is
  the only environment that reproduces this and there's no remote
  debugging session available.
  **Finally resolved, same day - not a code bug at all.** The debug
  output read `code 1: User denied Geolocation` - genuine
  `PERMISSION_DENIED`, confirmed real, but that string is identical
  whether Chrome is showing a fresh prompt the user just denied or
  silently refusing because of prior history; it carries no more
  information than the code itself. A screen recording, examined frame
  by frame (extracting every single frame across the ~0.5-1.5s window,
  not just every 5th), pinned the actual failure to under 70ms between
  "Requesting your location..." appearing and the denial replacing it -
  nowhere near enough time for a real lookup or human interaction,
  confirming Chrome was refusing before attempting anything. A screenshot
  of Chrome's own Location settings page then showed "Location access is
  off for this device" at that specific moment - genuinely off, contrary
  to an earlier claim of having enabled it - which explained that one
  data point but not the full pattern, since the user's mental model
  (a website popping up an "enable device location" dialog and turning
  it on for you, like Google Maps or a dating app can) turned out to
  describe a native-Android-only capability (Google Play Services'
  Location Settings API) that no website - not this one, not any -
  has ever had access to; a plain browser can only ask "may this site
  know your location," and only once system location is already on.
  The actual resolution came from the user's own diagnostic idea:
  checking production (`main`, untouched by any of this session's
  location-mode work) side by side with staging on the same phone -
  production worked normally. Diffing every location-relevant file
  between the branches found `frontend/index.html`, `public/sw.js`,
  `public/manifest.webmanifest`, and `backend/app.py` byte-identical,
  and the `getCurrentPosition()` call structurally the same shape in
  both (staging's current `enableHighAccuracy:false, timeout:20000` is
  if anything more lenient than production's original
  `true`/`10000`) - no code explanation survived a direct comparison.
  Confirmed conclusively by testing both sites in two browsers that had
  never visited either origin before (Firefox, Samsung Internet): both
  production and staging worked normally in both. Root cause: Chrome
  tracks geolocation permission independently per origin, and staging's
  specific hostname had been hit with an extraordinary number of
  repeated geolocation requests over the course of this one debugging
  session (automated verification passes plus manual retries) - almost
  certainly enough to trigger Chrome's own documented "quiet permissions"
  auto-suppression for that one origin specifically, a mechanism entirely
  separate from the explicit per-site "Blocked" list the user had already
  checked and reset. Production's origin, tested far less, never crossed
  that threshold. Not reproducible by a real first-time visitor to either
  environment, and not fixable (or breakable) by any code change - the
  `debugLocationError` diagnostic was removed once this was confirmed.
  Lesson for next time: when a bug is 100% reproducible on one specific
  URL in one specific browser but nothing about the code or the browser's
  own settings explains it, checking whether the *identical* code
  behaves differently on a *different origin* (or in a browser with no
  history on either) isolates "the app" from "this specific origin's
  accumulated browser-side state" far faster than continuing to audit
  the code or hunt through settings menus.

- Pre-public security hardening (2026-09-11) - triggered by making the
  GitHub repo public. Went through a generic "things AI-built apps forget"
  checklist someone sent the user item by item against the actual codebase
  (not applied wholesale) and implemented the real gaps found:
  - **Input length caps** - `ChatRequest.message` and `LocationLinkRequest.
    text` (`backend/app.py`) had no length limit; a pasted wall of text
    would have gone straight into a paid per-token Anthropic call. Added
    `Field(max_length=500)` to both, plus a matching `maxLength={500}` on
    the two frontend inputs (`ChatInput.tsx`, `LocationForm.tsx`) so
    hitting the cap fails as an ordinary input limit, not a raw 422.
  - **Security response headers** - none existed at all. Added a
    `security_headers` middleware (`backend/app.py`, ahead of the existing
    `cache_control` one) setting `X-Content-Type-Options`,
    `X-Frame-Options: DENY`, `Referrer-Policy`,
    `Strict-Transport-Security`, and a real `Content-Security-Policy`
    scoped to exactly what the app loads (same-origin scripts/API calls,
    the Google Fonts stylesheet + font files, `data:` for the inline SVG
    favicon - nothing else). `Permissions-Policy` explicitly keeps
    `geolocation=(self)` allowed (the app's core feature) while locking
    out camera/microphone/payment/usb, which it never uses. Verified live:
    zero console/CSP violations, a full chat round-trip (location set,
    real LLM query, real results) still worked end-to-end, and all 121
    backend tests still pass.
  - **`robots.txt`** - added (`frontend/public/robots.txt`, blanket
    `Disallow: /`), served from `/robots.txt` via a dedicated FastAPI
    route (`backend/app.py`) mirroring the existing `/sw.js` pattern -
    crawlers only ever check the true root, never `/static/robots.txt`.
    This was the one item from Roadmap #3 below actually built so far;
    custom 404, the error boundary, and the privacy policy from that same
    item are still open (an earlier summary of this roadmap incorrectly
    called all of #3 "done" - it was only ever "scoped").
  - **Social preview (OG/Twitter meta tags)** - added to
    `frontend/index.html` (`og:type`/`title`/`description`/`image`,
    `twitter:card`/`title`/`description`). Specifically worth doing here
    since the app already has a WhatsApp share button - a shared link
    with no preview card was undermining a feature that already existed.
    `og:image` deliberately points at the root-relative
    `/static/icons/icon-512.png` (already-existing PWA icon, reused
    rather than adding a new asset) rather than a hardcoded host, since
    production and staging sit on two different auto-generated Azure
    hostnames with no shared domain to hardcode.
  Explicitly NOT done as part of this pass, left as manual follow-ups for
  the user (outside what code changes can accomplish):
  - **Azure spend cap** - the $15/month figure is a stated goal, not an
    enforced budget alert. No Azure CLI access from this environment to
    set one up directly - needs a one-time manual "Cost Management >
    Budgets" setup in the Azure Portal.
  - **Confirm HTTPS-only enforcement** - Azure App Service serves HTTPS by
    default on its `azurewebsites.net` hostnames, but the explicit
    "HTTPS Only" toggle in the Portal wasn't directly verifiable from
    here either - worth a quick manual check.
  Also explicitly NOT relevant yet, and deliberately left alone rather
  than pre-built: admin-route/permission checks, CSRF protection, secure
  cookies, and secure file uploads - none of these have anything to
  protect yet (no auth, no cookies, no uploads exist), and each is already
  correctly sequenced to land alongside the feature that actually
  introduces it (see "Bigger builds - user system" below).
- Finished the rest of Roadmap #3 (2026-09-11): custom 404, error
  boundary, and privacy policy - `robots.txt` was the only piece of this
  item actually built in the security-hardening pass above; an earlier
  session summary incorrectly called the whole item "done" when it had
  only ever been "scoped."
  - **Custom 404 page** - a standalone, bilingual, on-theme static page
    (`frontend/public/404.html`, `frontend/public/pages.css` -
    deliberately an external stylesheet, not an inline `<style>` block,
    so the strict `style-src` CSP added in the hardening pass above
    covers it too without needing a CSP exception). Served via a new
    `custom_404_handler` app-level exception handler
    (`backend/app.py`) that returns this page for any 404 EXCEPT under
    `/api/` - those are the frontend's own `fetch` calls, which expect
    JSON, not an HTML page, so they keep FastAPI's default JSON 404
    unchanged.
  - **React error boundary** - `frontend/src/components/ErrorBoundary.tsx`,
    a class component (React only exposes `componentDidCatch`/
    `getDerivedStateFromError` as a class API, no hook equivalent exists)
    wrapping `<App />` in `main.tsx`. Reads the language preference
    directly via `loadLang()` rather than trusting any of App's own state,
    since the whole point is catching a crash *inside* App. Shows a
    simple "something broke, refresh" message with a reload button,
    styled via theme.css/App.css tokens (already loaded before the crash,
    so still available even if App's own render throws).
  - **Privacy policy page** - `frontend/public/privacy.html`, served at a
    clean `/privacy` URL the same way as `/sw.js`/`/robots.txt`. Written
    to accurately match what the code actually does (checked
    `services/routing.py`, `services/location.py`, `services/llm.py`, and
    the usage-stats collections directly, not assumed): location and
    typed addresses are forwarded to OSRM/Nominatim for routing/geocoding
    but never stored; chat messages go to Anthropic's Claude API and are
    never stored server-side (conversation lives only in browser memory,
    per the existing conversational-refinement design); the two
    anonymous usage-stats collections (category counts, unmatched-query
    text with its existing 90-day TTL) are disclosed as anonymous and
    curation-only; language/theme preferences are disclosed as
    browser-local-storage-only. Linked from a small, unobtrusive
    `<footer>` in `App.tsx` (a text link, not a header icon - the header
    is already flagged elsewhere in this file as too cramped to keep
    adding controls to), opened in a new tab via `target="_blank"` so
    visiting it doesn't lose the current (in-memory-only, no persistence)
    conversation in the original tab.
  Verified live: `/privacy` and an arbitrary unknown path both render
  correctly (bilingual, correct light/dark palette via
  `prefers-color-scheme`, since these standalone pages predate the
  React app's own theme-toggle logic); `/api/nonexistent` still returns
  JSON 404 unchanged; zero CSP violations or console errors; the footer
  link renders correctly (and mirrors position under RTL) in both
  languages; all 121 backend tests and the frontend typecheck still pass.

### Deferred (explicitly, revisit later)
- Public transit ETA — needs Google Distance Matrix (real cost/setup
  tradeoff vs. the free OSRM walk/drive ETAs already in place)
- Multi-curator map uploads — the review flagged this as the one roadmap
  item with real growth-loop shape (each curator brings their own
  network), and proposed a low-cost pilot (one hand-picked second
  curator, one-month trigger) to test that hypothesis before building the
  general self-serve feature. The user's explicit 2026-09-24 call: hold
  entirely for now, not even the pilot - stay single-curator for the
  foreseeable future. Revisit if that changes; the general build still
  needs the KML parser hardened first (`defusedxml`, size caps, per-user
  namespacing) either way.

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
11-12. Feedback option for bad data, and saved/frequent addresses - both
    superseded by the theme+horizon restructure; see "## Roadmap" above
    (Next horizon, Trust and Usability themes respectively). The privacy
    constraint on saved addresses carries forward unchanged: no semantic
    labels like "Home"/"Work" - those would let anyone, including the app
    operator, infer where a specific user actually lives or works, which
    this app has no business collecting.
13. ~~Price tag per place~~ - done end-to-end 2026-09-12: app-side
    implementation shipped 2026-09-11, and the user finished hand-tagging
    all the real pins in My Maps the next day. A manually-triggered run of
    `.github/workflows/sync_places.yml` (`workflow_dispatch`, rather than
    waiting for the 4am UTC cron) pulled the tags in immediately - synced
    165 places (one fewer than the 166 priced/tagged, since a place was
    separately removed from the map in between - unrelated to pricing).
    Verified live on real production data: a real "coffee" query showed
    real `$` chips (Mae Cafe, Origem Fresh Coffee, Chacho's), a real
    "steak" query showed real `$$$` chips (מיטבר, M25, Triger) - correct
    variety, not just a single hardcoded tier. Decided against the Google
    Places API option considered below - went with the hand-tagged
    approach instead, priced via a one-time Google Maps lookup pass
    rather than the paid API (see "Sourcing the actual price data" below
    for how that lookup was done). Also explicitly considered and
    declined: backfilling `price_tier` directly into MongoDB instead of
    tagging My Maps - would have needed `price_tier` switched from
    `dietary_tags`' always-overwrite-on-sync behavior to
    `instagram_url`'s preserve-on-update behavior first (otherwise the
    very next automatic sync would silently wipe every DB-only value back
    to empty, since the pins would still have no backing tag) - and even
    then, price would become the one field permanently disconnected from
    the map, editable only via a direct DB change rather than a normal
    pin edit like everything else in this app. The user chose to keep
    price consistent with how dietary tags/categories/Instagram links all
    already work instead.
    - **Hand-tagged, like dietary tags** - reuses the exact free-form
      hashtag pattern already working for `#kosher`/`#vegan` in a pin's
      My Maps description (see "Kosher/dietary tags and filtering"
      above) - `#$`, `#$$`, or `#$$$` in a pin's description. Zero new
      cost or integration.
    - `backend/parser.py` gained `_PRICE_RE` (`#(\${1,3})(?!\$)`), kept
      deliberately separate from `_TAG_RE`/`dietary_tags` rather than
      folded in - `$` isn't a `\w` character so it wouldn't match
      `_TAG_RE` anyway, and a place has exactly one price tier, not an
      open set like dietary tags. A price hashtag with more than 3 `$`
      signs (a likely typo, e.g. `#$$$$`) is rejected outright rather
      than silently truncated to `$$$`.
    - `Place.price_tier: Literal["$", "$$", "$$$"] | None` in
      `backend/models.py`; added to `PLACES_JSON_SCHEMA` in `backend/db.py`
      too (the `warn`-mode validator, same defense-in-depth as every
      other field). `scripts/sync_places.py` refreshes it on every sync,
      following `dietary_tags`' always-overwrite behavior (not
      `instagram_url`'s preserve-on-update behavior) - source-of-truth is
      always the map, same reasoning as dietary tags. `format_place()` in
      `backend/app.py` includes it in the API response.
    - Frontend: `PlaceCard.tsx` renders a `price-chip` (a `Banknote`
      lucide icon + the raw `$`/`$$`/`$$$` text - deliberately a
      different icon from the plain-text category/tag chips, so it reads
      as a distinct kind of fact at a glance rather than another tag) right
      after the category chip, only when `price_tier` is set. No i18n
      translation needed for the symbols themselves (universal), but added
      a `priceLabel` i18n key ("Price range"/"טווח מחירים") as the chip's
      `title` tooltip.
    - Verified live (via a temporary client-side fetch-response patch,
      since no real place has a price tag yet - see below) in both
      languages/themes/directions and at mobile width: chip renders
      correctly, no layout regression, RTL ordering matches the existing
      category chip. All 129 backend tests (8 new: parser price
      extraction incl. the "more than 3 `$`" rejection case, the model's
      `Literal` validation, `format_place` inclusion) and the frontend
      typecheck pass.
    - **Sourcing the actual price data (2026-09-11)**: rather than pay for
      the Google Places API, a background agent worked through all 166
      places on the live map, searching each by name+coordinates on
      Google Maps and reading off its price data (Israeli Google Maps
      shows a shekel range like "₪1–50", not $ symbols - bucketed into
      $/$$/$$$ by the range's low end: ≤50 -> $, 51-149 -> $$, >=150 ->
      $$$). Ran in batches of 12 with a 150s pause between batches
      (explicit user instruction, to avoid tripping Google's bot
      detection) - completed all 166 with zero CAPTCHA/blocks. 158 found
      cleanly, 6 found-but-no-Google-price-data, 2 the automated lookup
      itself failed on (one collapsed to a generic address/building match
      instead of the real business - the exact failure mode this
      session's earlier manual pilot had already surfaced once; one had
      its search term auto-corrected by Google to an unrelated chain).
      All 8 gaps were resolved by the user by hand afterward. Real lesson
      from the two failures: text-based name search can quietly resolve
      to the wrong thing even for an exact name match, which is a genuine
      argument for the real place_id-based Places API over scraping if
      this data ever needs a bulk refresh again. The final 166-place
      dataset lives at `price_results.json` in that session's scratchpad -
      not committed to the repo (scratch data, not app code) - and was
      fully hand-typed into My Maps by the user the next day (see above).

Explicitly considered and left out for now (2026-09-11): a persistent
dietary/category filter UI (vs. today's conversational, per-query
filtering) - revisit once favorites/the user system make session-level
state worth adding.

### Visual upgrades
- Category icons on the chips, and generating a formal `DESIGN.md`, are
  still open - not part of the three-perspective review's scope, so
  tracked as a loose end under "## Roadmap" above rather than placed on a
  horizon yet. (Map view has its own entry under "## Roadmap" -> Later,
  added 2026-09-24.)
- "Plan ahead for the header before it's forced" (2026-09-11) - resolved
  2026-09-13: the slide-out menu drawer (see "Bigger builds - user
  system" below) replaced the whole header icon row with two fixed
  elements (title + hamburger), structurally closing this concern rather
  than just working around it.
- Considered and declined for now (2026-09-11): a distinct visual badge
  for "surprise me" results (e.g. marking those cards differently from a
  normal category match) - not needed at this scale.
- Design polish pass, done via the third-party "Taste Skill" project skills
  (`.claude/skills/`, installed via `npx skills add Leonxlnx/taste-skill` -
  a separate "Impeccable" skill was tried too but its installer was blocked
  by this environment's safety classifier). Ran the `redesign-existing-
  projects` skill's audit checklist honestly against the actual codebase
  rather than applying it wholesale - most of its checklist items were
  already satisfied from earlier work this session (the warm/dark palettes
  were a deliberate prior choice, not an AI default; `100dvh` was already
  used correctly; the pill/soft-radius system was already consistent;
  lucide-react was kept since the project already depends on it, which the
  skill itself carves out as an exception). Four real, targeted gaps got
  fixed:
  - Added subtle, hue-tinted `box-shadow`s (`--shadow-sm`/`--shadow-md` in
    `theme.css`, warm-tinted in light mode, a dark shadow + faint top
    highlight in dark mode) to bubbles and place cards, which had zero
    depth/elevation before - pure border-only flat cards.
    place cards also get a `:hover` shadow lift.
  - Added `:hover` states to every button that only had `:active` press
    feedback before (mode toggle, share, show-more, retry-location, the
    filled Set/Send pills) - previously zero desktop mouse feedback until
    the moment of click.
  - Standardized icon stroke width across the whole app to one consistent
    value via a single `.app svg { stroke-width: 2.5 }` rule (CSS overrides
    an SVG's own stroke-width attribute) instead of the one-off
    `strokeWidth={2.5}` that only `MapPin` had - a real, if minor,
    inconsistency the redesign skill's audit specifically flags.
  - `scroll-behavior: smooth` on the chat log (guarded by
    `prefers-reduced-motion`) so new messages scroll into view instead of
    snapping, plus `text-wrap: pretty` on bubble text.
  Deliberately left alone: the sun/moon theme toggle (the skill flags this
  as a generic pattern, but replacing it with a settings dropdown would be
  a real usability regression at this app's mobile-first, low-chrome
  scale - a tradeoff, not a clear defect).
- Impeccable design critique + hardening pass (2026-09-10) - once the user
  installed the "Impeccable" skill themselves (its own installer is blocked
  by this environment's sandbox, same as the earlier Taste Skill attempt;
  see the Roadmap), ran `/impeccable critique` as a genuine second design
  pass on top of the Taste Skill polish above. Dual-agent review (isolated
  design read + a deterministic anti-pattern scan plus live-browser
  evidence) scored the app 31/40 ("Good") - the full report is persisted at
  `.impeccable/critique/2026-09-10T18-00-25Z__frontend-src-app-tsx.md`.
  Of the 5 findings (2 P1, 2 P2, 1 P3), fixed the two P1s via
  `/impeccable harden` (the user's explicit scope for this pass - the P2s
  and P3 are deliberately still open, see that snapshot file):
  - **RTL bidi bug + misaligned Hebrew-name cards** - real, live-reproduced
    on actual data (a Hebrew-named place, "קפליקס" at critique time):
    `PlaceCard`'s `.distance-eta` span had no explicit `dir`, so the
    Unicode bidi algorithm visually reordered "0.24 km · 4 min" into
    "km · 4 min 0.24" even in an English-language card; separately, only
    the `.name` div had `dir="auto"`, so a Hebrew name floated top-right
    while the rest of the card (chips, buttons) stayed left-aligned
    underneath it. Fixed by moving `dir="auto"` up to the whole
    `.place-card` (so every child follows the name's own resolved
    direction consistently, not just the name text itself) and pinning
    `.distance-eta` to `dir="ltr"` unconditionally, since it's always
    digits and Latin units regardless of the name's script or the UI
    language. Verified live in Hebrew UI, light and dark, desktop and
    mobile: a Hebrew-named result card now aligns name/chips/buttons to
    the same edge, and the distance/ETA text reads correctly regardless.
  - **Light-mode contrast failures** - `--muted` (location status line,
    every place-card's distance/ETA text, tag chips) computed to ~3.5:1
    against `--bg`, and white button/bubble text on `--accent` computed to
    ~3.1:1 - both below WCAG AA's 4.5:1 for normal text. Fixed by darkening
    both in `theme.css`'s light-mode `:root` block only (dark mode wasn't
    flagged and is untouched): `--muted` `#a97c64` → `#8a5c42` (~5.4:1),
    `--accent` `#ff5a36` → `#c23f19` (already present in the palette as
    `--chip-fg`, so not a new color - ~4.6-5.2:1 across every context it's
    used in as text, and as a background under white text). `--bubble-user`
    - a separate token that happened to share the old accent's exact hex
      value by design - got the identical fix for the identical reason
      (white message text on a user's own chat bubble is the single most
      visible surface this bug touched, even though it's technically a
      different CSS variable from `--accent`).
  Deliberately not run yet: `/impeccable polish` as a broader pass (the
  skill's own closing step after a harden) - the source diff for these two
  fixes was already clean (no accidental churn), so there was nothing left
  for a broader polish pass to do within this scope.
  Followed up the same day with the P2s and P3 from the same critique
  snapshot:
  - **"Surprise me" was undiscoverable without finding Help first** - the
    chat input placeholder swapped its second example from a mundane
    category ("coffee") to the actually-novel feature: `chatPlaceholder`
    now reads "...e.g. 'ramen' or 'surprise me'" (Hebrew: "תפתיע אותי",
    reusing the exact phrase already established in the help text) in
    `i18n.ts`. Deliberately a placeholder swap, not an extra greeting
    bubble - always visible without adding conversation noise.
  - **No way to reset a conversation** - a `RotateCcw` icon button
    ("New conversation" / "שיחה חדשה") added to the header's icon row
    (`Header.tsx`, between theme and help), wired to a new
    `handleNewConversation` in `App.tsx` that calls `setEntries([])` and
    nothing else - deliberately leaves `userLocation`, `theme`, and `lang`
    untouched, so starting over doesn't also discard location permission
    or re-prompt for it. Verified live: sent a query, got real results,
    clicked reset (log cleared back to just the pinned greeting), sent a
    second query immediately after with no location form appearing -
    confirming location state survived the reset.
  - **Undersized header touch targets** - `.icon-button` (theme, the new
    reset button, and help - all icon-only) computed to ~28-32px per side,
    under the 44x44px comfortable mobile target. Added `min-width: 44px` /
    `min-height: 44px` in `App.css` - grows the invisible hit area only,
    icon visual size unchanged. Verified live via `getBoundingClientRect()`
    on all four header buttons: all now exactly 44px tall, 44-54px wide
    (the language toggle is wider because of its "EN"/"עברית" text label).
  This closes all 5 findings from the 2026-09-10 critique snapshot - next
  step, if wanted, is re-running `/impeccable critique` to confirm the
  score improved from 31/40.
  Separately, the typing-indicator's `bounce-easing` detector finding
  (App.css, `.typing-indicator span`) - the one the user had explicitly
  chosen to keep as a deliberate chat-app idiom - got revisited once seen
  side-by-side: built a live comparison widget of the current bounce
  against a suggested exponential-ease-out alternative, and the user
  preferred the suggested version after actually seeing both. Swapped the
  keyframes from an asymmetric `0%/30%/60%/100%` bounce under `ease-in-out`
  to a symmetric `0%/50%/100%` `rise-fall` under
  `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out-expo) - same 1.1s duration and
  0.15s/0.3s per-dot stagger, so only the curve shape changed. Verified live
  via `getComputedStyle` mid-animation. The now-stale `bounce-easing=bounce`
  ignore-list entry in `.impeccable/config.json` was left in place rather
  than hand-edited out (no CLI command removes a single ignore-value entry,
  and the config file isn't meant to be hand-edited) - it's inert now that
  nothing in the CSS matches "bounce" anymore, not incorrect.
- Re-ran `/impeccable critique` (2026-09-10, second snapshot:
  `.impeccable/critique/2026-09-10T19-29-46Z__frontend-src-app-tsx.md`) to
  verify the harden-pass fixes rather than taking them on faith. Score moved
  31 -> 28/40 - a real drop, not noise: the dual-agent re-run (fresh design
  review + detector/browser evidence, isolated and parallel, same as the
  first run) independently measured and confirmed all 5 previous fixes held
  up (real pixel measurements on touch targets, real contrast ratios, real
  DOM inspection of a Hebrew-named place card from live data), but also
  found a genuine regression the harden pass introduced: moving
  `dir="auto"` from just `.name` to the whole `.place-card` fixed the
  original single-card misalignment, but made each card's *entire layout*
  (not just its text) follow its own place name's script independently -
  so a mixed-language results list (normal for this dataset) had the
  Navigate/Instagram buttons visibly swap sides card-to-card while
  scrolling. Fixed by dropping `dir="auto"` from `.place-card` entirely
  (`PlaceCard.tsx`) - every card in a list now follows the *page's* own
  language consistently (all cards left-align together in English UI, all
  right-align together in Hebrew UI, regardless of which script an
  individual name is in), trading "each name aligns per its own script"
  for "every card in a list looks the same" - the user confirmed this
  tradeoff explicitly before it was implemented. A Hebrew name's own
  characters still render in correct reading order via standard Unicode
  bidi even without the dir override; only the block-level alignment/button
  position is now uniform. Verified live via DOM measurement
  (`getBoundingClientRect`) in both languages: all cards in one list now
  agree on which side the Navigate button sits, including a genuinely
  Hebrew-named result ("קפה אחד העם") sitting next to English-named ones
  in the same scroll. `.distance-eta`'s `dir="ltr"` pin was untouched (not
  part of the regression).
  The re-critique also surfaced 3 issues, all now fixed (see below and the
  snapshot file for the full original writeups).
- Fixed the destructive "New Conversation" P2 from the same re-critique -
  clicking it wiped the chat log instantly with no confirmation or undo,
  ~4.8px from Theme/Help in the header's icon row (an easy mis-tap on
  mobile). Chose the undo-toast option over widening the button gap or
  adding a confirmation dialog (the user's call): `handleNewConversation`
  (`App.tsx`) now stashes the just-cleared `entries` in a new
  `clearedEntries` state instead of discarding them, clears the visible
  log, and starts a 5s timer (`UNDO_WINDOW_MS`); a bar above the composer
  (`.undo-toast`, styled from the existing chip/pill tokens) offers "Undo"
  for that window. Two deliberate guards beyond the timer: clicking Reset
  on an already-empty log is a no-op (nothing to stash, per the critique's
  own suggested fix), and sending a new message immediately forfeits any
  pending undo (`dismissUndo()` at the top of `handleSend`) - otherwise a
  stale Undo click after continuing the conversation would silently
  discard whatever the user just sent, trading one data-loss bug for
  another. Verified live in both languages: clear -> undo restores all
  3 cards and hides the toast; clear -> wait 5s auto-dismisses; clear ->
  send a new message immediately hides the toast (no dangling undo); RTL
  mirrors correctly (label right, Undo button left, matching the app's
  existing RTL flow).
- Fixed the unlabeled-header-buttons P2 from the same re-critique - Theme,
  Reset, and Help were icon-only with no visible label or tooltip (only
  the language toggle pairs icon+text), so a first-time user had to tap
  and see to learn what a button did - risky for Reset given it's
  destructive. Added a native `title` attribute to each of the three
  (`Header.tsx`), mirroring its existing `aria-label` so the hover tooltip
  and the screen-reader name always say the same thing in the current
  language. Deliberately the lighter of the critique's two suggested
  fixes (tooltip vs. promoting all three to visible icon+text labels like
  the language toggle) - full labels would widen an already-flagged
  6-control header on narrow mobile viewports, going against this
  project's earlier explicit call to keep the header icon-only rather
  than add a settings dropdown (see "Visual upgrades" below). Screen
  readers already had the destructive Reset button's name via
  `aria-label`, and it's no longer a silent, unrecoverable action either
  - the undo toast above covers that risk directly. Verified live in both
  languages that `title` now matches `aria-label` exactly on all three
  buttons, and that the language toggle correctly has no `title` (it
  already carries a visible label).
- Fixed the input-focus-ring P3 from the same re-critique, closing out all
  5 of its findings - `.chat-form input:focus` and `.location-form-row
  input:focus` explicitly set `outline: none` and substituted only a
  1.5px border-color shift, a visibly weaker cue than every button's
  native focus outline. Added `box-shadow: 0 0 0 3px color-mix(in srgb,
  var(--accent) 35%, transparent)` alongside the existing border-color
  change on both rules (`App.css`) - a `color-mix()`-derived accent-tinted
  ring rather than a hardcoded rgba, so it automatically follows whichever
  `--accent` value is active (rust in light mode, lime in dark) with no
  per-theme override needed. `document.hasFocus()` is false in this
  sandbox's automated browser pane by default (it isn't the OS-focused
  window), which silently suppresses `:focus` entirely regardless of CSS -
  a real synthetic keyboard event (Tab) rather than a programmatic
  `.focus()` call was needed to get a trustworthy read; confirmed via
  `getComputedStyle` afterward that both inputs, in both themes, correctly
  resolve the ring to a real color (not `none` or invalid).
- Re-ran `/impeccable critique` a third time (2026-09-10, snapshot
  `.impeccable/critique/2026-09-10T20-45-17Z__frontend-src-app-tsx.md`) to
  verify the second harden pass. Score trend: 31 -> 28 -> 34/40 - all 4
  issues from the second critique were independently re-verified with
  strong evidence (byte-identical undo restore, identical bounding-rect
  positions across mixed-language cards, exact tooltip/aria-label matches,
  a real `getComputedStyle` focus-ring read backed by a genuine
  `document.hasFocus() === true` this time). But the `title`-tooltip fix
  for unlabeled header icons turned out to only partially work: `title`
  only ever surfaces on mouse hover, which does nothing for a touchscreen
  - and this is explicitly a mobile-first app (the PWA work earlier was
  built specifically for phone installs). Fixed by giving the "New
  Conversation" button specifically (the one destructive action among the
  three) a visible text label matching the language toggle's existing
  icon+text pattern (`Header.tsx`) - Theme and Help stay icon-only with
  their `title` tooltip, per the user's explicit choice to label only the
  destructive one rather than all three. This widened that button enough
  to break the header's layout at narrow mobile widths (the title and the
  action row started fighting for space, wrapping "New conversation" mid-
  phrase) - fixed by letting `.header-top` wrap onto two rows
  (`flex-wrap: wrap`) with `white-space: nowrap` on the title so it wraps
  as a whole unit instead of mid-word, and `margin-inline-start: auto` on
  `.header-actions` so the action row stays pinned to the same edge
  whether or not it's sharing a row with the title. Verified live at
  375px in both languages: title and actions each stay on one line,
  wrapping cleanly onto two rows instead of squeezing or breaking mid-
  phrase, and the action row keeps its RTL/LTR-correct edge either way.
- Fixed the header-icon-gap P2 from the same (third) re-critique -
  `.header-actions`'s `gap` was still `0.3rem` (~4.8px between adjacent
  44x44 touch targets), unchanged by the label fix above, which addressed
  discoverability but not the tap-target spacing that made an accidental
  Reset tap easy in the first place. Widened to `0.6rem` (`App.css`),
  landing in the critique's own suggested 8-12px range. Verified live via
  `getBoundingClientRect()` on all four header buttons: every adjacent
  gap now measures exactly 9.6px, in both languages and at both mobile
  (375px) and desktop widths, with no wrapping regression from the
  now-slightly-wider header-actions row.
- Fixed the inconsistent-focus-ring P3 from the same (third) re-critique,
  closing out all 3 of its findings - buttons and links still relied on
  the browser's bare default outline while text inputs had a custom
  accent `box-shadow` ring, so the indicator's character changed
  depending on what kind of element you tabbed onto. Added one global
  rule (`.app button:focus-visible, .app a:focus-visible`, `App.css`)
  using the same `color-mix()`-based accent ring already on the inputs,
  and switched the two existing input rules from `:focus` to
  `:focus-visible` so every interactive element in the app is now
  governed by the same pseudo-class, not just visually matching under
  different trigger conditions. `:focus-visible`'s own browser heuristic
  does the right thing here for free - it only engages for keyboard-driven
  focus on buttons/links (confirmed live: a mouse click on a button does
  NOT trigger the ring, `el.matches(':focus-visible')` correctly `false`),
  while text inputs still show it on any focus method (browsers always
  treat text fields as wanting a visible indicator) - so switching their
  rule to `:focus-visible` changed nothing about when their ring appears,
  only which selector governs it. Verified live via real keyboard Tab
  presses (not programmatic `.focus()`, which can produce an
  unrepresentative read - see the earlier focus-ring entry above) across
  the language toggle, theme toggle, and a place-card's Navigate link -
  all three render the identical ring as the text inputs.
- Re-ran `/impeccable critique` a fourth time (snapshot
  `.impeccable/critique/2026-09-10T21-29-56Z__frontend-src-app-tsx.md`).
  Score trend: 31 -> 28 -> 34 -> 36/40 - the best yet, and every one of
  the third critique's 3 fixes was independently re-verified with hard
  numbers (9.59px header gaps in both languages, byte-identical
  focus-ring `box-shadow` across a button/link/input, confirmed real
  rendered text - not just `aria-label` - on the reset button). This run
  found two smaller things:
  - **Place-card names skip `ChatBubble`'s `dir="auto"` treatment** -
    genuinely true, and CLAUDE.md's own Hebrew-support writeup above was
    stale on this point (it used to say place-card names got the same
    treatment, back when they did - see "Production/staging environment
    split" below for the two rounds where that was tried and reverted).
    Presented the tradeoff directly rather than picking a side: fixing
    it naively (adding `dir="auto"` back to just `.name`) would reintroduce
    a milder version of the very first RTL bug, since the name would
    text-align differently from its own card's chips/buttons. The user
    confirmed leaving it as-is - the documentation above is now corrected
    to explain why, so a future pass doesn't "fix" this same thing a
    third time.
  - **Chat placeholder truncated mid-word on narrow phones** (375px,
    320px) - "What are you craving? e.g. 'ramen' or 'surprise me'" clipped
    to "...e.g. 'rame" with no ellipsis. Fixed with a standard
    `overflow: hidden; white-space: nowrap; text-overflow: ellipsis;` on
    `.chat-form input` (`App.css`) - reads as intentional truncation
    instead of a mid-word chop, in both languages (confirmed the ellipsis
    renders on the correct/start side under Hebrew's RTL too). Doesn't
    affect real typed input, which is always short-lived per keystroke.
  Also surfaced by both this run and the third: pressing Enter appeared
  not to submit the chat form in the sandboxed browser pane. Confirmed a
  false alarm after deploying to staging and testing on a real device -
  Enter-to-send works correctly; the automation environment's synthetic
  keypresses just weren't a faithful stand-in for a real Enter press in
  this case. No code change was needed.

### Bigger builds - user system (sequenced, not started)
Goal: real accounts usable by friends and family now, with an eye toward a
full product later.
1. ~~Auth core~~ - app-side implementation done 2026-09-12, built and tested
   against staging per the roadmap's own instruction, not production. Real
   end-to-end sign-in with an actual Google account still needs the user to
   verify by hand - session/user-management sessions can't complete a real
   Google OAuth login (that needs a real account and, appropriately,
   Claude never handles a user's real credentials).
   - **Google Sign-In (OAuth) as the actual front door, not self-managed
     passwords** - delegates credential security (storage, breach
     detection, reset flows) entirely to Google. Explicitly considered and
     declined: a parallel bcrypt/salted-password system as a fallback for
     anyone who doesn't want Google Sign-In - doubles the security surface,
     needs a new email-sending dependency for password resets (real cost,
     against the $15/month budget), and reopens exactly the risk
     delegating to Google was meant to close. The mitigation instead: the
     base chat stays fully anonymous regardless (see below) - nobody is
     locked out of the *product*, only the not-yet-built extras
     (favorites/ratings/suggestions) that will actually require an account.
   - **Google Identity Services' ID-token flow**, not the older full
     OAuth 2.0 authorization-code redirect dance - this app only needs to
     know who someone is, not act on their behalf against Google's APIs,
     so the simpler client-side flow (a rendered button hands the frontend
     a signed ID token directly) is the right fit. Needs only "Authorized
     JavaScript origins" configured on the Google Cloud OAuth Client ID,
     no redirect URIs.
   - **New Google Cloud project + OAuth Client ID**, deliberately created
     under a separate Google account from the user's personal one (the
     user's own call, not a security requirement - the Client ID isn't
     secret, it ends up in the frontend's own public code either way; the
     real reason was not wanting a personal email shown on the consent
     screen during real sign-ins, plus general hygiene keeping side-project
     cloud resources off a personal account). Authorized JavaScript
     origins cover local dev (`localhost:8000` uvicorn, `localhost:5173`
     Vite dev server) plus both the real staging and production Azure
     hostnames.
   - **Backend**: `User` model (`backend/models.py`) keyed on Google's
     `sub` claim, not email (Google's own guidance - email can change,
     sub never does) - `google_sub`, `email`, `name`, `picture_url`,
     `token_version` (bumped on sign-out, see below), `created_at`. A
     `users` collection (`db.py`) with a unique index on `google_sub` and
     its own `$jsonSchema` warn-mode validator, same defense-in-depth
     pattern as `places`. `_ensure_schema_validator` was generalized to
     take a collection name + schema rather than being hardcoded to
     `places`, now that a second collection needs one.
   - **`backend/services/auth.py`** (new, matching the one-module-per-
     integration pattern already used for `llm`/`routing`/`location`):
     wraps Google's own token verification (`google-auth`'s
     `id_token.verify_oauth2_token`, checked against this app's own Client
     ID as the audience - without that check, a token issued for a
     completely different Google app would also pass) and issues this
     app's own JWTs (`PyJWT`) - a short-lived access token (15 min, held
     only in browser memory, never localStorage) and a longer-lived
     refresh token (30 days, `httpOnly`/`Secure`/`SameSite=Strict` cookie,
     scoped to `/api/auth` only rather than the whole site). Both tokens
     carry a `type` claim (`access`/`refresh`) specifically so a leaked
     refresh token - which page JS should never even be able to read -
     can't also be replayed as an access token. Every refresh call rotates
     the refresh token too (not reused for its full 30-day life), and
     compares the token's embedded `token_version` against the user's
     current stored value - a sign-out bumps that value
     (`db.revoke_user_sessions`), instantly invalidating every refresh
     token ever issued to that user, not just the one in the browser that
     clicked sign-out.
   - **New endpoints**: `POST /api/auth/google` (verify credential, look
     up or create the user, issue tokens), `POST /api/auth/refresh`
     (rotate access+refresh from the cookie), `POST /api/auth/logout`
     (revoke + clear cookie), `GET /api/auth/me`, `GET /api/auth/config`
     (serves `GOOGLE_CLIENT_ID` to the frontend - not secret, but kept as
     one source of truth in the backend's own env rather than duplicated
     into a frontend build-time config, same reasoning as fetching
     `/api/categories` instead of hardcoding). Nothing existing calls the
     required-auth dependency (`get_current_user_id`) yet - it's built and
     ready for the first feature (favorites) that actually needs it.
   - **CSP had to grow for Google Identity Services specifically** (three
     real, live-discovered requirements, not assumed upfront):
     `script-src`/`connect-src`/`frame-src` need `https://accounts.google.com`
     for the script itself, its network calls, and the One Tap/consent
     iframe; `img-src` needs `https://*.googleusercontent.com` for profile
     pictures; and `style-src` needed `'unsafe-inline'` added - GIS injects
     its own inline styles at runtime that can't be pre-hashed/nonced, and
     also loads a stylesheet from `https://accounts.google.com/gsi/style`.
     Inline *style* injection carries a much smaller blast radius than
     inline *script* would, and this app has no user-generated HTML
     rendering path that could exploit it, so this was judged an
     acceptable, narrow loosening rather than a broad one.
   - **Frontend**: `GoogleSignInButton.tsx` loads Google's script itself
     (no npm package - GIS isn't officially published as one anyway, and
     this matches the project's existing habit of hand-rolling rather than
     adding a dependency, same reasoning as the hand-rolled i18n) and
     renders Google's own full branded button (`text: 'signin_with'`).
     A first version tried an icon-only variant directly in the header row
     to avoid widening it - abandoned once the design below made that
     unnecessary.
   - **`AccountControl.tsx` is a menu, not a bare button** (2026-09-12,
     the user's own suggestion) - a single 44px account icon in the header
     (a generic person-circle icon signed out, the real avatar/a colored
     initial fallback signed in) opens a panel; the panel's *contents*
     change with auth state (the Google button signed out, name + sign-out
     signed in), not the trigger itself. Deliberately designed this way so
     favorites/saved-spots get a home in this same panel once they exist,
     instead of each new account-scoped feature fighting for its own
     header slot - directly answers this file's own earlier note under
     "Visual upgrades" about the header needing deliberate planning before
     auth and manual-location both wanted presence in it. This replaced an
     earlier version that rendered the Google button (icon-only,
     `type: 'icon'`/`shape: 'circle'`) directly in the header row - abandoned
     for two reasons: it didn't match the "small avatar in a slot" design
     actually agreed on, and it caused a real, live-reproduced horizontal
     overflow at 375px once sitting alongside the existing 4 header
     controls.
   - **The rendered button's own language didn't automatically follow
     this app's language toggle** - a real bug caught live, not assumed:
     Google's button text is baked into the specific script Google serves,
     keyed by an `hl` query param on the script URL itself; without it,
     Google falls back to the browser/OS locale (or an existing Google
     session's own language), independent of this app's own `lang` state.
     Fixed by appending `?hl=<lang>` to the script src, reloading the
     script (removing and re-adding the tag - changing `hl` on an
     already-loaded script has no effect) when the language differs from
     what's currently loaded.
   - **Reloading that script while the button stayed mounted turned out to
     be genuinely flaky under rapid toggling** - live-reproduced, not
     theoretical: toggling the language twice in quick succession (while
     the button was permanently mounted in the header, in the earlier
     design) left Google's rendered iframe missing its own background
     styling on the second reload. The menu redesign above fixes this as
     a side effect, not just a coincidence: `GoogleSignInButton` now only
     ever mounts while the panel is open (conditional rendering in
     `AccountControl.tsx` unmounts it entirely on close), so a language
     change made while the panel is closed is picked up fresh the next
     time it opens, rather than the component having to tear down and
     reload Google's script while already alive and rendered. Reacting to
     a *theme* change while the panel stays open is still handled the
     original way (a plain re-render via `renderButton`, no script reload
     needed - only `hl` requires a fresh script), since that's cheap and
     never showed the same flakiness.
   - **Second real-device report (2026-09-12): the account icon itself
     needed horizontal scrolling to reach in English on mobile** - the
     header's icon row (language, theme, new conversation, help, account -
     5 controls by this point) had gone from "fits" to "doesn't" as
     controls accumulated, exactly the risk this file's own "Visual
     upgrades" section had flagged as inevitable before auth and manual-
     location both wanted header presence. Fixed with a proper redesign
     rather than another squeeze: the entire icon row is now a single
     hamburger button (`Menu` icon) that opens a full-height slide-out
     drawer (`SideMenu.tsx`, new) containing all 4 of those controls as
     full-width labeled rows, with the account section (renamed
     `AccountControl.tsx` -> `AccountSection.tsx`, now pure content with
     no trigger/popover of its own) pinned to the drawer's bottom via
     `margin-top: auto` - the user's own suggestion, and explicitly framed
     as the future home for favorites/saved-spots too, not just account.
     The header now holds exactly two things regardless of auth or
     language state - the title and one hamburger - so this class of
     overflow bug structurally can't recur as more controls get added
     later; they go in the drawer, not the header.
     Drawer mechanics: a fixed-position panel anchored via
     `inset-inline-end: 0` (RTL-safe positioning, flips automatically),
     animated with `transform: translateX(100%|0)` - `transform` itself
     does NOT respect logical/RTL directions the way `inset-inline-end`
     already does, so closed-state translateX is flipped explicitly under
     `[dir='rtl']` rather than assumed symmetric. A backdrop dims and
     click-closes the page behind it; `inert` is applied to the whole
     drawer while closed (keyboard/screen-reader focus can't reach hidden
     content); Escape closes it too. Selecting any item closes the drawer
     afterward (`selectAndClose`), matching how the old popover closed
     itself after sign-out.
     Verified via direct CSS specificity/computed-style inspection
     (`element.matches()`, and forcing `transition: none` to read the
     final resolved `transform` instantly) rather than trusting visual
     screenshots alone - this session's Browser pane was hidden/
     backgrounded for part of this verification, which throttles CSS
     transitions and `requestAnimationFrame` entirely (confirmed: the
     computed transform was flat-out wrong mid-"transition" until forcing
     it, then immediately correct) - a real browser tab a real person has
     open and focused doesn't have this problem, but it's worth recording
     since it looked exactly like a real animation bug at first before the
     `transition: none` test isolated it as a hidden-tab artifact instead.
     Confirmed no horizontal overflow at 375px in either language (the
     actual reported bug) - the header's own two-element row can no
     longer overflow no matter how much the drawer's own contents grow.
   - App.tsx holds the session directly (no Context API, no extra
     abstraction - matches how the rest of this app's state already
     works): an access token in a ref (deliberately not state, since
     nothing in the UI reads its raw value, only whether someone is
     signed in), a `User | null` in state, and a scheduled silent-refresh
     timer (14 minutes, just under the real 15-minute access-token expiry)
     that keeps a session alive transparently across a long visit as long
     as the refresh token itself is still valid. A silent
     `/api/auth/refresh` call on every page load restores a session from
     the cookie if one exists; a fresh visitor with no cookie gets a plain
     401 that resolves to "signed out," not a thrown error anywhere in the
     UI.
   - Verified live (real browser, all 4 light/dark x en/he combinations,
     and 375px mobile width, both on this session's local dev server and
     the real deployed staging environment): the account menu opens and
     closes (including click-outside-to-close), the Google button inside
     it renders correctly in the language/theme active at open time with
     zero console/CSP errors, and there's no horizontal overflow anywhere
     tested - including the panel itself at 375px, positioned against the
     header's edge the same way the header's own controls already are.
     All 157 backend tests pass (28 new: JWT issue/verify/rotation
     including the access-vs-refresh type-confusion cases, the `users`
     collection CRUD functions, and all 5 new endpoints, all mocked -
     zero real Google/Atlas calls in the suite, matching the existing
     "mint a JWT directly for a test user" plan).
   - **`GOOGLE_CLIENT_ID`/`JWT_SECRET` added to both staging's and
     production's real Azure App Settings** (a distinct, randomly-generated
     `JWT_SECRET` per environment, never reused). **Real end-to-end
     sign-in verified by the user on the real deployed staging
     environment** with an actual Google account - confirmed working.
   - **The signed-out account icon was nearly invisible in light mode** -
     a real bug the user caught live on a real device, not something any
     of this session's own testing reproduced (every check up to that
     point had been in the sandboxed browser tool). Root cause: unlike
     `.icon-button` and every other header control, `.account-avatar-button`
     never set its own `color`, so it fell back to the browser's native
     default button text color - which on that real device resolved to
     white, invisible against the light theme's cream background,
     completely independent of this app's own light/dark toggle. Fixed
     by explicitly setting `color: var(--muted)` (matching `--muted`'s
     already-verified WCAG AA contrast from the earlier Impeccable
     hardening pass), plus a `:hover` state matching `.icon-button`'s.
   - **Verified live on the real deployed staging environment** (real
     phone, both languages) after the slide-out drawer redesign above -
     no horizontal overflow, hamburger opens/closes the drawer correctly,
     account section pinned at the bottom as designed, RTL and both
     themes render correctly. Pushed to `main` and deployed to production
     2026-09-13 - auth core (item 1's whole scope, including this drawer
     redesign) is now live for real users, not just staging.
2-5. Favorites, Ratings, user-suggested places, and map uploads -
   superseded by the theme+horizon restructure; see "## Roadmap" above
   (Next: Favorites, and the private "I'd go back" signal that Ratings
   resolved into; Later: user-suggested places; Deferred: multi-curator
   map uploads, held entirely as of 2026-09-24). Ratings and multi-curator
   uploads were flagged as open tensions by the review and resolved by
   the user that same day, rather than sitting in this flat sequence
   unexamined.

Update (2026-09-10): the tradeoff flagged here already happened, sooner
than expected - not from real friends-and-family traffic, but from this
session's own deploy/restart activity while setting up the environment
split (see "Production/staging environment split" above). Production is
now on Basic (B1), which has no CPU-minute cap at all, so this specific
risk is resolved for production going forward. Staging remains on Free
F1 and could in principle hit the same cap under heavy test traffic, but
that's a much lower-stakes failure mode now that it's fully isolated from
production.
