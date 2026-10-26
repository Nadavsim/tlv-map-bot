import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db
from .models import PlaceResult
from .services import auth, llm, location, routing, streets

load_dotenv()

# Uvicorn only wires up its own loggers, so without a handler here the app's
# own INFO lines (e.g. routing.py's per-call OSRM timing) are silently
# dropped. Scoped to the "backend" namespace on purpose - turning INFO on
# globally would also surface every third-party library's chatter.
_app_log_handler = logging.StreamHandler()
_app_log_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
logging.getLogger("backend").addHandler(_app_log_handler)
logging.getLogger("backend").setLevel(logging.INFO)

# .parent.parent, not .parent: this file lives in backend/, but static/ (built
# by frontend/'s Vite build) sits at the repo root, a sibling of backend/.
BASE_DIR = Path(__file__).parent.parent

# Protects the project's budget goal: /api/chat is the expensive route (one
# Anthropic call + Mongo + OSRM per request), and until now nothing stopped
# repeated/automated hits from running up real cost. Per-IP, in-memory (this
# runs as a single Azure App Service instance, so no shared store needed).
# 20/minute allows a real rapid back-and-forth conversation; 200/day is a
# backstop for a shared IP (e.g. a household) without allowing sustained abuse.
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.ensure_indexes()
    yield


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.exception_handler(StarletteHTTPException)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    # /api/* callers are the frontend's own fetch code, not a browser
    # navigation - they expect JSON, not an HTML page, on a bad request.
    # Everything else (a stray/bookmarked/typo'd URL) gets the branded page.
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        return FileResponse(BASE_DIR / "static" / "404.html", status_code=404)
    return await http_exception_handler(request, exc)


@app.middleware("http")
async def security_headers(request, call_next):
    """Baseline hardening headers, same on every response. CSP is scoped to
    exactly what the app actually loads: same-origin scripts/API calls, the
    Google Fonts stylesheet + font files, data: URIs for the inline SVG
    favicon, and (since Google Sign-In) Google Identity Services' own script/
    frame/network calls and Google-hosted profile pictures. The map view
    adds exactly one more origin, to img-src only: OpenStreetMap's tile
    server (Leaflet loads tiles as plain <img> elements, so nothing else -
    no connect-src/script-src - is needed). Nothing else.
    Permissions-Policy explicitly keeps geolocation available to the page
    itself (the app's core feature) while locking out unrelated device APIs
    this app never uses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "geolocation=(self), camera=(), microphone=(), payment=(), usb=()"
    )
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://accounts.google.com; "
        # 'unsafe-inline' here is specifically for Google Identity Services -
        # it injects its own inline styles at runtime that can't be
        # pre-hashed/nonced. Inline *style* injection (unlike script) has a
        # much smaller blast radius, and this app has no user-generated HTML
        # rendering path that could exploit it.
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https://*.googleusercontent.com https://tile.openstreetmap.org; "
        "connect-src 'self' https://accounts.google.com; "
        "frame-src https://accounts.google.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    return response


@app.middleware("http")
async def cache_control(request, call_next):
    """index.html must always be revalidated - it's what points the browser
    at the current build's asset filenames. Everything under /static/assets/
    is Vite's content-hashed output (a new build gets new filenames), so it
    can be cached aggressively forever with zero staleness risk."""
    response = await call_next(request)
    if request.url.path.startswith("/static/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache"
    return response


PriceTier = Literal["$", "$$", "$$$"]


class ChatRequest(BaseModel):
    # Capped well above any real craving/follow-up message - mainly a guard
    # against someone pasting a huge blob into the (paid, per-token) LLM call.
    message: str = Field(max_length=500)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    lang: Literal["en", "he"] = "en"
    # Just enough of the previous turn for the LLM to recognize a refinement
    # ("something else", "another one") without real conversation history -
    # held entirely on the frontend (derived from the last places result),
    # not a server-side session, so it's naturally short-lived (gone on
    # reload). previous_category=None with has_previous_context=True means
    # the previous turn was "any category" (surprise me), not "no previous
    # turn at all" - that distinction is what has_previous_context is for.
    # Bounded because previous_category/previous_dietary_tag are echoed into the
    # paid LLM prompt: a real value is a short category or tag name.
    previous_category: str | None = Field(default=None, max_length=60)
    previous_dietary_tag: str | None = Field(default=None, max_length=60)
    previous_price_tier: PriceTier | None = None
    previous_offset: int = Field(default=0, ge=0, le=1000)
    has_previous_context: bool = False


class LocationLinkRequest(BaseModel):
    # A Maps link, coordinate pair, or address never needs to be this long -
    # same reasoning as ChatRequest.message.
    text: str = Field(max_length=500)


class MorePlacesRequest(BaseModel):
    category: str | None = Field(default=None, max_length=60)
    tag: str | None = Field(default=None, max_length=60)
    price: PriceTier | None = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    offset: int = Field(ge=0, le=1000)


# Matches the top-N shown per request on both the initial match and each
# "show more" page - the frontend uses it to detect "that was the last page"
# (a page shorter than this means there's nothing left to fetch).
PAGE_SIZE = 3

# Fixed reply strings per UI language. Category names themselves (from the
# DB, e.g. "coffee") are deliberately NOT translated here even in the
# Hebrew replies - translating them would need a maintained EN->HE mapping
# that goes stale as the map's categories change, which is exactly what the
# help command's live category list (see the frontend) was built to avoid.
REPLIES = {
    "en": {
        "empty_db": "The places database is empty. Run `python -m scripts.sync_places` to load places first.",
        "no_category_fallback": "Not sure what you're craving - can you tell me a type of food?",
        "no_matches": "I don't have any {label} spots saved yet.",
        "no_matches_with_tag": "I don't have any {tag} {label} spots saved yet.",
        "no_more_matches": "That's all the {label} spots I have saved for now.",
        "no_more_matches_with_tag": "That's all the {tag} {label} spots I have saved for now.",
        "matched": "Here are the closest {category} spots:",
        "matched_with_tag": "Here are the closest {tag} {category} spots:",
        "surprise": "Surprise! Here are the closest spots overall:",
        "surprise_with_tag": "Here are the closest {tag} spots overall:",
        "any_label": "any",
        "price_words": {"$": "cheap", "$$": "mid-range", "$$$": "high-end"},
        "qualifier_sep": " ",
        "assistant_unavailable": "Sorry, I couldn't work that out just now - please try again in a moment.",
        "unsupported_note": 'I don\'t have "{what}" marked on my list yet.',
        "closest_overall": "Here are the closest spots overall:",
    },
    "he": {
        "empty_db": "מסד הנתונים של המקומות ריק. הרץ `python -m scripts.sync_places` כדי לטעון מקומות קודם.",
        "no_category_fallback": "לא ברור לי מה מתחשק לך - תוכל לספר לי איזה סוג אוכל?",
        "assistant_unavailable": "סליחה, לא הצלחתי להבין את זה כרגע - נסה שוב בעוד רגע.",
        "unsupported_note": 'עדיין אין לי סימון של "{what}" ברשימה.',
        "closest_overall": "הנה המקומות הכי קרובים בסך הכל:",
        "no_matches": "עדיין אין לי מקומות מסוג {label} שמורים.",
        "no_matches_with_tag": "עדיין אין לי מקומות מסוג {label} ({tag}) שמורים.",
        "no_more_matches": "אלה כל המקומות מסוג {label} ששמורים אצלי כרגע.",
        "no_more_matches_with_tag": "אלה כל המקומות מסוג {label} ({tag}) ששמורים אצלי כרגע.",
        "matched": "הנה המקומות הכי קרובים מסוג {category}:",
        "matched_with_tag": "הנה המקומות הכי קרובים מסוג {category} ({tag}):",
        "surprise": "הפתעה! הנה המקומות הכי קרובים בסך הכל:",
        "surprise_with_tag": "הנה המקומות הכי קרובים בסך הכל ({tag}):",
        "any_label": "כלשהו",
        "price_words": {"$": "זול", "$$": "בינוני", "$$$": "יקר"},
        "qualifier_sep": ", ",
    },
}


def replies_for(lang: str) -> dict:
    return REPLIES.get(lang, REPLIES["en"])


def _qualifier(dietary_tag: str | None, price_tier: str | None, replies: dict) -> str | None:
    """The price word and/or tag, as one phrase the reply templates drop in
    where a bare tag used to go ("closest cheap vegan coffee spots"), so each
    template doesn't need a variant per price/tag combination."""
    parts = [w for w in (replies["price_words"].get(price_tier), dietary_tag) if w]
    return replies["qualifier_sep"].join(parts) or None


def _no_results_reply(
    base_key: str, category: str | None, dietary_tag: str | None, price_tier: str | None, replies: dict
) -> str:
    label = category or replies["any_label"]
    qualifier = _qualifier(dietary_tag, price_tier, replies)
    if qualifier:
        return replies[f"{base_key}_with_tag"].format(tag=qualifier, label=label)
    return replies[base_key].format(label=label)


def _places_reply(
    category: str | None,
    dietary_tag: str | None,
    price_tier: str | None,
    any_category: bool,
    matches: list,
    offset: int,
    replies: dict,
    unsupported: str | None = None,
) -> dict:
    qualifier = _qualifier(dietary_tag, price_tier, replies)
    if any_category:
        if qualifier:
            reply = replies["surprise_with_tag"].format(tag=qualifier)
        else:
            # "Surprise!" is for "surprise me"; after an honest "I can't filter
            # by that" it would read as a gimmick.
            reply = replies["closest_overall"] if unsupported else replies["surprise"]
    elif qualifier:
        reply = replies["matched_with_tag"].format(tag=qualifier, category=category)
    else:
        reply = replies["matched"].format(category=category)
    if unsupported:
        # Said plainly instead of silently ignoring what was asked for.
        reply = f"{replies['unsupported_note'].format(what=unsupported)} {reply}"
    return {
        "reply": reply,
        # Distance only: the ETA needs a call to a public routing service that
        # stalls now and then, so it is fetched separately (/api/etas) after
        # the places are already on screen.
        "places": [format_place(p) for p in matches],
        # Echoed back so the frontend can ask for more of the same query
        # (via /api/more-places, or a natural-language follow-up like
        # "something else") without re-running the LLM categorization.
        "category": category,
        "dietary_tag": dietary_tag,
        "price_tier": price_tier,
        "offset": offset,
    }


def format_place(place: PlaceResult, eta_seconds: float | None = None) -> dict:
    distance_km = place.distance / 1000
    distance_str = f"{distance_km:.2f} km" if distance_km < 1 else f"{distance_km:.1f} km"

    lon, lat = place.location.coordinates
    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"

    return {
        # Stable reference to this exact place (favorites point at it).
        "id": place.id,
        "name": place.name,
        "category": place.category,
        "distance": distance_str,
        "eta": routing.format_duration(eta_seconds) if eta_seconds is not None else None,
        "instagram_url": place.instagram_url,
        "dietary_tags": place.dietary_tags,
        "price_tier": place.price_tier,
        "closes_at_hour": place.closes_at_hour,
        "outdoor_seating": place.outdoor_seating,
        "maps_url": maps_url,
        # GeoJSON order is [lon, lat] - unpacked above, returned by name so
        # no caller (the map view) has to remember which way round it is.
        "lat": lat,
        "lon": lon,
    }


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/sw.js")
async def service_worker():
    # Served from the root path (not /static/sw.js) on purpose: a service
    # worker's default scope is its own script's directory, and the scope
    # must cover the manifest's start_url ("/") for Chrome to consider the
    # app installable as a PWA.
    return FileResponse(BASE_DIR / "static" / "sw.js", media_type="application/javascript")


# GET and HEAD: external uptime monitors commonly probe with HEAD (some can't
# be switched to GET on a free plan), and a 405 there reads as "down" forever.
@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    # Wired into Azure App Service's built-in Health Check feature (General
    # settings -> Health check, point it at this path) so a hung or
    # DB-disconnected instance gets auto-restarted instead of silently
    # serving errors - this app has already failed silently once, with
    # nobody alerted, during the prod/staging split. A non-200 here is a
    # real signal, not a formality: it means the database is unreachable.
    if not await db.ping_database():
        raise HTTPException(status_code=503, detail="database unreachable")
    return {"status": "ok"}


@app.get("/robots.txt")
async def robots():
    # Same reasoning as /sw.js - crawlers only ever look at the true root,
    # never /static/robots.txt. This app is friends-and-family only, not
    # meant for public discovery, hence the blanket disallow.
    return FileResponse(BASE_DIR / "static" / "robots.txt", media_type="text/plain")


@app.get("/privacy")
async def privacy():
    # A clean root-level URL (mirrors /sw.js, /robots.txt) rather than
    # pointing people at /static/privacy.html directly.
    return FileResponse(BASE_DIR / "static" / "privacy.html")


@app.get("/about")
async def about():
    # Same shape as /privacy: a static, bilingual page, clean root-level URL.
    return FileResponse(BASE_DIR / "static" / "about.html")


async def _count_location_outcome(key: str) -> None:
    """Best-effort anonymous counter (see db.LOCATION_UNRESOLVED_KEY) - a
    database hiccup must never turn a "not found" into an error."""
    try:
        await db.record_category_request(key)
    except Exception:
        logging.getLogger(__name__).warning("couldn't record location outcome counter %s", key)


@app.post("/api/resolve-location")
@limiter.limit("20/minute;200/day")
async def resolve_location(request: Request, req: LocationLinkRequest):
    text = req.text.strip()
    coords, place_text = await asyncio.to_thread(location.resolve_maps_link_detail, text)
    if not coords:
        # No coordinates in the text or its expanded link. A link is looked up
        # by the place text it carries (and never sent to the address geocoder
        # as a raw URL - useless there, and a link can hold more than a
        # place); anything else is a free-text address/landmark.
        is_link = "http://" in text or "https://" in text
        queries = (location.geocode_candidates(place_text) if place_text else []) if is_link else [text]
        suggestion = None
        try:
            for query in queries:
                coords = await asyncio.to_thread(location.geocode_address, query)
                if coords:
                    break
            if not coords and not is_link:
                # Nothing for the text as typed: if it looks like a misspelt
                # street, find where the corrected spelling would be. It is
                # offered, never applied - the person confirms it.
                corrected = streets.suggest_correction(text)
                if corrected:
                    corrected_coords = await asyncio.to_thread(location.geocode_address, corrected)
                    if corrected_coords:
                        suggestion = {"text": corrected, "lat": corrected_coords[0], "lon": corrected_coords[1]}
        except location.GeocodingUnavailable:
            # 503, not the nulls below: "couldn't look it up right now" and
            # "that address doesn't exist" need different messages - the
            # frontend turns any non-OK response into its "try again" copy.
            raise HTTPException(status_code=503, detail="geocoding service unavailable")
        if suggestion:
            await _count_location_outcome(db.LOCATION_CORRECTION_OFFERED_KEY)
            return {"lat": None, "lon": None, "suggestion": suggestion}
    if not coords:
        await _count_location_outcome(db.LOCATION_UNRESOLVED_KEY)
        return {"lat": None, "lon": None}
    lat, lon = coords
    # For a link, the place's own text is a better label than the URL the
    # person pasted; None for typed text, which is its own label.
    is_link = "http://" in text or "https://" in text
    return {"lat": lat, "lon": lon, "label": place_text if is_link else None}


@app.get("/api/categories")
async def categories():
    return {"categories": await db.get_categories()}


@app.post("/api/chat")
@limiter.limit("20/minute;200/day")
async def chat(request: Request, req: ChatRequest):
    replies = replies_for(req.lang)

    known_categories = await db.get_categories()
    if not known_categories:
        return {"reply": replies["empty_db"], "places": []}

    known_dietary_tags = await db.get_dietary_tags()
    extraction = await llm.parse_food_request(
        req.message,
        known_categories,
        req.lang,
        dietary_tags=known_dietary_tags,
        previous_category=req.previous_category,
        previous_dietary_tag=req.previous_dietary_tag,
        has_previous_context=req.has_previous_context,
        previous_price_tier=req.previous_price_tier,
    )

    # The model call failed: say so, count it on its own and stop. Falling
    # through would log the visitor's text as an "unmatched" craving and ask
    # them a cuisine question, which is wrong and hides an outage.
    if extraction.get("llm_failed"):
        await _count_location_outcome(db.LLM_FAILED_KEY)
        return {"reply": replies["assistant_unavailable"], "places": []}

    # Something the visitor asked for that the list can't honour ("vegan" with
    # no vegan pins, "open now"): never silently dropped. The reply says so,
    # and the text goes to the curator's unmatched log - it is exactly "what
    # people want that the map doesn't have yet".
    unsupported = extraction.get("unsupported")
    if unsupported:
        try:
            await db.log_unmatched_query(req.message)
        except Exception:
            logging.getLogger(__name__).warning("couldn't log an unsupported request")

    # A refinement of the previous turn ("something else", "another one",
    # "cheaper") - keep the same category/tag (or "any", if that's what the
    # previous turn was) and continue past what was already shown, rather
    # than treating this message as its own fresh, independent request.
    if req.has_previous_context and extraction["is_followup"]:
        category = req.previous_category
        dietary_tag = req.previous_dietary_tag
        # A follow-up that names a price ("cheaper") swaps it in; otherwise
        # the previous price keeps applying to "something else".
        price_tier = extraction["price_tier"] or req.previous_price_tier
        # Offset only means something against the same filters: a changed
        # price is a different result set, so it starts from the top.
        offset = req.previous_offset if price_tier == req.previous_price_tier else 0
        await db.record_category_request(category or db.ANY_CATEGORY_KEY)
        matches = await db.find_nearest(
            category, req.lat, req.lon, limit=PAGE_SIZE, offset=offset, tag=dietary_tag, price=price_tier
        )
        if not matches:
            return {
                "reply": _no_results_reply(
                    "no_more_matches" if offset else "no_matches", category, dietary_tag, price_tier, replies
                ),
                "places": [],
                "category": category,
                "dietary_tag": dietary_tag,
                "price_tier": price_tier,
                "offset": offset,
            }
        return _places_reply(
            category, dietary_tag, price_tier, category is None, matches, offset + len(matches), replies, unsupported
        )

    if not extraction["any_category"] and not extraction["category"]:
        await db.log_unmatched_query(req.message)
        await db.record_category_request(db.UNMATCHED_KEY)
        return {
            "reply": extraction["clarifying_question"] or replies["no_category_fallback"],
            "places": [],
        }

    category = extraction["category"]
    dietary_tag = extraction["dietary_tag"]
    price_tier = extraction["price_tier"]
    await db.record_category_request(category or db.ANY_CATEGORY_KEY)
    matches = await db.find_nearest(category, req.lat, req.lon, limit=PAGE_SIZE, tag=dietary_tag, price=price_tier)
    if not matches:
        return {
            "reply": _no_results_reply("no_matches", category, dietary_tag, price_tier, replies),
            "places": [],
            "category": category,
            "dietary_tag": dietary_tag,
            "price_tier": price_tier,
        }

    return _places_reply(
        category, dietary_tag, price_tier, extraction["any_category"], matches, len(matches), replies, unsupported
    )


@app.post("/api/more-places")
@limiter.limit("20/minute;200/day")
async def more_places(request: Request, req: MorePlacesRequest):
    matches = await db.find_nearest(
        req.category, req.lat, req.lon, limit=PAGE_SIZE, offset=req.offset, tag=req.tag, price=req.price
    )
    if not matches:
        return {"places": []}

    return {"places": [format_place(p) for p in matches]}


class EtaDestination(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class EtaRequest(BaseModel):
    mode: Literal["walking", "driving"] = "walking"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    # A results block is PAGE_SIZE places; the cap is just a guard against a
    # caller turning a free public routing service into a bulk matrix tool.
    destinations: list[EtaDestination] = Field(min_length=1, max_length=10)


@app.post("/api/etas")
@limiter.limit("40/minute;400/day")
async def etas(request: Request, req: EtaRequest):
    """Travel times for places the client already has on screen. Kept apart
    from /api/chat and /api/more-places so a slow or failing routing service
    can never hold up the results themselves: the places arrive at once with
    distance only and each card fills its ETA in when this answers. A null
    entry means "no ETA available" (unreachable, or routing is down) and the
    card simply keeps showing distance, as it always has."""
    seconds = await routing.get_eta_seconds_batch(
        req.mode,
        (req.lat, req.lon),
        [(d.lat, d.lon) for d in req.destinations],
    )
    return {"etas": [routing.format_duration(s) if s is not None else None for s in seconds]}


class PlaceReportRequest(BaseModel):
    place_id: str = Field(min_length=1, max_length=64)
    kind: Literal["closed", "wrong_category", "would_return"]


@app.post("/api/place-reports")
@limiter.limit("10/minute;60/day")
async def report_place(request: Request, req: PlaceReportRequest):
    """A visitor telling the curator something about a place: it's closed,
    it's in the wrong category, or they'd go back. Open to signed-out
    visitors on purpose (most visitors have no account) and anonymous on
    purpose: only the place, the kind and a running count are stored, never
    who sent it. It changes nothing other visitors see - "I'd go back" in
    particular is private to the curator and never becomes a rating shown to
    anyone; the list stays the curator's call."""
    status = await db.record_place_report(req.place_id, req.kind)
    if status == "no_place":
        raise HTTPException(status_code=404, detail="Place not found")
    return {"ok": True}


# --- Auth ---------------------------------------------------------------
# Google Sign-In only (see CLAUDE.md for why no self-managed password path
# exists) - the base chat above stays fully usable with zero login; this
# section exists to unblock future features (favorites, ratings) that do
# need to know who's asking, not to gate anything that exists today.

REFRESH_COOKIE_NAME = "refresh_token"
# Scoped to /api/auth specifically, not the whole site - the cookie has no
# reason to be sent along with every place/chat/static-asset request.
REFRESH_COOKIE_PATH = "/api/auth"


class GoogleAuthRequest(BaseModel):
    # Field name matches Google Identity Services' own callback payload
    # (`response.credential`) - one less translation for the frontend to do.
    credential: str = Field(max_length=4096)


def _user_public_dict(user) -> dict:
    return {"name": user.name, "email": user.email, "picture_url": user.picture_url}


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        max_age=auth.REFRESH_TOKEN_TTL_SECONDS,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )


async def get_current_user_id(authorization: str | None = Header(None)) -> str:
    """Required-auth dependency - raises 401 if there's no valid access
    token. Nothing uses this yet (see the section note above), but it's
    here ready for the first endpoint that needs it."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = auth.decode_access_token(authorization.removeprefix("Bearer "))
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


@app.get("/api/auth/config")
async def auth_config():
    # The Client ID isn't secret - it's already public in the frontend's own
    # bundle either way - this just avoids hardcoding it in two places.
    return {"google_client_id": auth.GOOGLE_CLIENT_ID}


@app.post("/api/auth/google")
async def auth_google(req: GoogleAuthRequest, response: Response):
    claims = auth.verify_google_id_token(req.credential)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    existing = await db.get_user_by_google_sub(claims["sub"])
    if existing:
        user_id, user = existing
    else:
        user_id, user = await db.create_user(
            google_sub=claims["sub"],
            email=claims["email"],
            name=claims["name"],
            picture_url=claims.get("picture"),
        )

    access_token = auth.create_access_token(user_id)
    _set_refresh_cookie(response, auth.create_refresh_token(user_id, user.token_version))
    return {"access_token": access_token, "user": _user_public_dict(user)}


@app.post("/api/auth/refresh")
async def auth_refresh(response: Response, refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME)):
    def unauthorized() -> HTTPException:
        response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
        return HTTPException(status_code=401, detail="Not authenticated")

    if not refresh_token:
        raise unauthorized()
    decoded = auth.decode_refresh_token(refresh_token)
    if not decoded:
        raise unauthorized()
    user_id, token_version = decoded

    user = await db.get_user_by_id(user_id)
    # A version mismatch means this refresh token predates a sign-out
    # (see db.revoke_user_sessions) - reject it even though it hasn't
    # expired yet, which is the entire point of tracking a version at all.
    if not user or user.token_version != token_version:
        raise unauthorized()

    access_token = auth.create_access_token(user_id)
    # Rotated (not reused) on every refresh - standard practice so a leaked
    # refresh token has a shrinking window of usefulness rather than staying
    # valid, unrotated, for the full 30 days.
    _set_refresh_cookie(response, auth.create_refresh_token(user_id, token_version))
    return {"access_token": access_token, "user": _user_public_dict(user)}


@app.post("/api/auth/logout")
async def auth_logout(response: Response, refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME)):
    if refresh_token:
        decoded = auth.decode_refresh_token(refresh_token)
        if decoded:
            user_id, _ = decoded
            # Bumps token_version, so this one call revokes every refresh
            # token ever issued to this user - not just the one in this
            # request's cookie (e.g. also signs out a different device).
            await db.revoke_user_sessions(user_id)
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(authorization: str | None = Header(None)):
    user_id = await get_current_user_id(authorization)
    user = await db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return _user_public_dict(user)


@app.delete("/api/auth/me")
async def auth_delete_account(response: Response, authorization: str | None = Header(None)):
    """Self-serve account deletion: removes the user record and everything
    tied to it (saved addresses, favorites). Authenticated by the bearer
    access token like every other account action, so it isn't reachable by
    a cross-site request (the cookie alone can't trigger it)."""
    user_id = await get_current_user_id(authorization)
    if not await db.delete_user(user_id):
        raise HTTPException(status_code=401, detail="User no longer exists")
    # Any refresh token still in circulation now points at no user and is
    # rejected by /api/auth/refresh; this just clears this browser's copy.
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    return {"ok": True}


# --- Saved addresses ----------------------------------------------------
# A signed-in person's frequently-used manual addresses (see
# models.SavedAddress for the privacy reasoning: no user-chosen names, capped,
# coordinates rounded). Account-only on purpose - the anonymous experience is
# unchanged - and nothing here is ever read by /api/chat: the frontend sends
# a saved address's coordinates like any other manual location.


class SavedAddressRequest(BaseModel):
    # What the person typed to set the location - bounded well under the
    # location box's own 500 cap, since only a short display text is kept.
    label: str = Field(max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


def _saved_address_dict(address) -> dict:
    return {"id": address.id, "label": address.label, "lat": address.lat, "lon": address.lon}


@app.get("/api/saved-addresses")
async def list_saved_addresses(authorization: str | None = Header(None)):
    user_id = await get_current_user_id(authorization)
    addresses = await db.list_saved_addresses(user_id)
    if addresses is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return {"addresses": [_saved_address_dict(a) for a in addresses], "max": db.MAX_SAVED_ADDRESSES}


@app.post("/api/saved-addresses")
async def add_saved_address(req: SavedAddressRequest, response: Response, authorization: str | None = Header(None)):
    user_id = await get_current_user_id(authorization)
    status, address = await db.add_saved_address(user_id, req.label, req.lat, req.lon)
    if status == "no_user":
        raise HTTPException(status_code=401, detail="User no longer exists")
    if status == "full":
        raise HTTPException(status_code=409, detail="Saved address limit reached")
    response.status_code = 201 if status == "added" else 200
    return {"address": _saved_address_dict(address)}


@app.delete("/api/saved-addresses/{address_id}")
async def delete_saved_address(address_id: str, authorization: str | None = Header(None)):
    user_id = await get_current_user_id(authorization)
    if not await db.remove_saved_address(user_id, address_id):
        raise HTTPException(status_code=404, detail="Saved address not found")
    return {"ok": True}


# --- Favorites ----------------------------------------------------------
# Account-only, like saved addresses. A favorite is just {user, place, when}:
# nothing about *why* (no notes, no ratings) and nothing visible to anyone but
# its owner. Shown back as ordinary result cards, nearest first.


class FavoriteRequest(BaseModel):
    place_id: str = Field(min_length=1, max_length=64)


@app.get("/api/favorites")
async def favorite_places(
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    authorization: str | None = Header(None),
):
    """Without lat/lon this is just the list (distances are meaningless then);
    with both, the same places nearest-first for the chat's card view."""
    if (lat is None) != (lon is None):
        raise HTTPException(status_code=422, detail="lat and lon go together")
    user_id = await get_current_user_id(authorization)
    places = await db.find_favorite_places(user_id, lat, lon)
    if places is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return {"places": [format_place(p) for p in places]}


@app.post("/api/favorites")
async def add_favorite(req: FavoriteRequest, response: Response, authorization: str | None = Header(None)):
    user_id = await get_current_user_id(authorization)
    status = await db.add_favorite(user_id, req.place_id)
    if status == "no_user":
        raise HTTPException(status_code=401, detail="User no longer exists")
    if status == "no_place":
        raise HTTPException(status_code=404, detail="Place not found")
    if status == "full":
        raise HTTPException(status_code=409, detail="Favorites limit reached")
    response.status_code = 201 if status == "added" else 200
    return {"id": req.place_id}


@app.delete("/api/favorites/{place_id}")
async def remove_favorite(place_id: str, authorization: str | None = Header(None)):
    user_id = await get_current_user_id(authorization)
    if not await db.remove_favorite(user_id, place_id):
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"ok": True}
