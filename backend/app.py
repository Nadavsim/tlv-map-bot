import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, Header, HTTPException, Request, Response
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
from .services import auth, llm, location, routing

load_dotenv()

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
    frame/network calls and Google-hosted profile pictures - nothing else.
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
        "img-src 'self' data: https://*.googleusercontent.com; "
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


class ChatRequest(BaseModel):
    # Capped well above any real craving/follow-up message - mainly a guard
    # against someone pasting a huge blob into the (paid, per-token) LLM call.
    message: str = Field(max_length=500)
    lat: float
    lon: float
    mode: Literal["walking", "driving"] = "walking"
    lang: Literal["en", "he"] = "en"
    # Just enough of the previous turn for the LLM to recognize a refinement
    # ("something else", "another one") without real conversation history -
    # held entirely on the frontend (derived from the last places result),
    # not a server-side session, so it's naturally short-lived (gone on
    # reload). previous_category=None with has_previous_context=True means
    # the previous turn was "any category" (surprise me), not "no previous
    # turn at all" - that distinction is what has_previous_context is for.
    previous_category: str | None = None
    previous_dietary_tag: str | None = None
    previous_offset: int = 0
    has_previous_context: bool = False


class LocationLinkRequest(BaseModel):
    # A Maps link, coordinate pair, or address never needs to be this long -
    # same reasoning as ChatRequest.message.
    text: str = Field(max_length=500)


class MorePlacesRequest(BaseModel):
    category: str | None = None
    tag: str | None = None
    lat: float
    lon: float
    mode: Literal["walking", "driving"] = "walking"
    offset: int


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
    },
    "he": {
        "empty_db": "מסד הנתונים של המקומות ריק. הרץ `python -m scripts.sync_places` כדי לטעון מקומות קודם.",
        "no_category_fallback": "לא ברור לי מה מתחשק לך - תוכל לספר לי איזה סוג אוכל?",
        "no_matches": "עדיין אין לי מקומות מסוג {label} שמורים.",
        "no_matches_with_tag": "עדיין אין לי מקומות מסוג {label} ({tag}) שמורים.",
        "no_more_matches": "אלה כל המקומות מסוג {label} ששמורים אצלי כרגע.",
        "no_more_matches_with_tag": "אלה כל המקומות מסוג {label} ({tag}) ששמורים אצלי כרגע.",
        "matched": "הנה המקומות הכי קרובים מסוג {category}:",
        "matched_with_tag": "הנה המקומות הכי קרובים מסוג {category} ({tag}):",
        "surprise": "הפתעה! הנה המקומות הכי קרובים בסך הכל:",
        "surprise_with_tag": "הנה המקומות הכי קרובים מסוג {tag}:",
        "any_label": "כלשהו",
    },
}


def replies_for(lang: str) -> dict:
    return REPLIES.get(lang, REPLIES["en"])


def _no_results_reply(base_key: str, category: str | None, dietary_tag: str | None, replies: dict) -> str:
    label = category or replies["any_label"]
    if dietary_tag:
        return replies[f"{base_key}_with_tag"].format(tag=dietary_tag, label=label)
    return replies[base_key].format(label=label)


def _places_reply(
    category: str | None,
    dietary_tag: str | None,
    any_category: bool,
    matches: list,
    etas: list,
    offset: int,
    replies: dict,
) -> dict:
    if any_category:
        reply = replies["surprise_with_tag"].format(tag=dietary_tag) if dietary_tag else replies["surprise"]
    elif dietary_tag:
        reply = replies["matched_with_tag"].format(tag=dietary_tag, category=category)
    else:
        reply = replies["matched"].format(category=category)
    return {
        "reply": reply,
        "places": [format_place(p, eta) for p, eta in zip(matches, etas)],
        # Echoed back so the frontend can ask for more of the same query
        # (via /api/more-places, or a natural-language follow-up like
        # "something else") without re-running the LLM categorization.
        "category": category,
        "dietary_tag": dietary_tag,
        "offset": offset,
    }


def format_place(place: PlaceResult, eta_seconds: float | None) -> dict:
    distance_km = place.distance / 1000
    distance_str = f"{distance_km:.2f} km" if distance_km < 1 else f"{distance_km:.1f} km"

    lon, lat = place.location.coordinates
    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"

    return {
        "name": place.name,
        "category": place.category,
        "distance": distance_str,
        "eta": routing.format_duration(eta_seconds) if eta_seconds is not None else None,
        "instagram_url": place.instagram_url,
        "dietary_tags": place.dietary_tags,
        "price_tier": place.price_tier,
        "maps_url": maps_url,
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


@app.post("/api/resolve-location")
async def resolve_location(req: LocationLinkRequest):
    text = req.text.strip()
    coords = await asyncio.to_thread(location.resolve_maps_link, text)
    if not coords:
        # Not a coordinate pair or a Maps link (or the link didn't resolve) -
        # try it as a free-text address/landmark instead.
        coords = await asyncio.to_thread(location.geocode_address, text)
    if not coords:
        return {"lat": None, "lon": None}
    lat, lon = coords
    return {"lat": lat, "lon": lon}


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
    )

    # A refinement of the previous turn ("something else", "another one") -
    # keep the same category/tag (or "any", if that's what the previous
    # turn was) and continue past what was already shown, rather than
    # treating this message as its own fresh, independent request.
    if req.has_previous_context and extraction["is_followup"]:
        category = req.previous_category
        dietary_tag = req.previous_dietary_tag
        await db.record_category_request(category or db.ANY_CATEGORY_KEY)
        matches = await db.find_nearest(
            category, req.lat, req.lon, limit=PAGE_SIZE, offset=req.previous_offset, tag=dietary_tag
        )
        if not matches:
            return {
                "reply": _no_results_reply("no_more_matches", category, dietary_tag, replies),
                "places": [],
                "category": category,
                "dietary_tag": dietary_tag,
                "offset": req.previous_offset,
            }
        etas = await routing.get_eta_seconds_batch(
            req.mode,
            (req.lat, req.lon),
            [(p.location.coordinates[1], p.location.coordinates[0]) for p in matches],
        )
        return _places_reply(
            category, dietary_tag, category is None, matches, etas, req.previous_offset + len(matches), replies
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
    await db.record_category_request(category or db.ANY_CATEGORY_KEY)
    matches = await db.find_nearest(category, req.lat, req.lon, limit=PAGE_SIZE, tag=dietary_tag)
    if not matches:
        return {
            "reply": _no_results_reply("no_matches", category, dietary_tag, replies),
            "places": [],
            "category": category,
            "dietary_tag": dietary_tag,
        }

    etas = await routing.get_eta_seconds_batch(
        req.mode,
        (req.lat, req.lon),
        [(p.location.coordinates[1], p.location.coordinates[0]) for p in matches],
    )
    return _places_reply(category, dietary_tag, extraction["any_category"], matches, etas, len(matches), replies)


@app.post("/api/more-places")
@limiter.limit("20/minute;200/day")
async def more_places(request: Request, req: MorePlacesRequest):
    matches = await db.find_nearest(
        req.category, req.lat, req.lon, limit=PAGE_SIZE, offset=req.offset, tag=req.tag
    )
    if not matches:
        return {"places": []}

    etas = await routing.get_eta_seconds_batch(
        req.mode,
        (req.lat, req.lon),
        [(p.location.coordinates[1], p.location.coordinates[0]) for p in matches],
    )
    return {"places": [format_place(p, eta) for p, eta in zip(matches, etas)]}


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
