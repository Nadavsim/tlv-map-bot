import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from . import db
from .models import PlaceResult
from .services import llm, location, routing

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
    message: str
    lat: float
    lon: float
    mode: Literal["walking", "driving"] = "walking"


class LocationLinkRequest(BaseModel):
    text: str


class MorePlacesRequest(BaseModel):
    category: str | None = None
    lat: float
    lon: float
    mode: Literal["walking", "driving"] = "walking"
    offset: int


# Matches the top-N shown per request on both the initial match and each
# "show more" page - the frontend uses it to detect "that was the last page"
# (a page shorter than this means there's nothing left to fetch).
PAGE_SIZE = 3


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
    known_categories = await db.get_categories()
    if not known_categories:
        return {
            "reply": "The places database is empty. Run `python -m scripts.sync_places` to load places first.",
            "places": [],
        }

    extraction = await llm.parse_food_request(req.message, known_categories)

    if not extraction["any_category"] and not extraction["category"]:
        await db.log_unmatched_query(req.message)
        await db.record_category_request(db.UNMATCHED_KEY)
        return {
            "reply": extraction["clarifying_question"]
            or "Not sure what you're craving - can you tell me a type of food?",
            "places": [],
        }

    category = extraction["category"]
    await db.record_category_request(category or db.ANY_CATEGORY_KEY)
    matches = await db.find_nearest(category, req.lat, req.lon, limit=PAGE_SIZE)
    if not matches:
        label = category or "any"
        return {
            "reply": f"I don't have any {label} spots saved yet.",
            "places": [],
            "category": category,
        }

    etas = await routing.get_eta_seconds_batch(
        req.mode,
        (req.lat, req.lon),
        [(p.location.coordinates[1], p.location.coordinates[0]) for p in matches],
    )

    reply = (
        "Surprise! Here are the closest spots overall:"
        if extraction["any_category"]
        else f"Here are the closest {category} spots:"
    )
    return {
        "reply": reply,
        "places": [format_place(p, eta) for p, eta in zip(matches, etas)],
        # Echoed back so the frontend can ask for more of the same query
        # (via /api/more-places) without re-running the LLM categorization.
        "category": category,
    }


@app.post("/api/more-places")
@limiter.limit("20/minute;200/day")
async def more_places(request: Request, req: MorePlacesRequest):
    matches = await db.find_nearest(req.category, req.lat, req.lon, limit=PAGE_SIZE, offset=req.offset)
    if not matches:
        return {"places": []}

    etas = await routing.get_eta_seconds_batch(
        req.mode,
        (req.lat, req.lon),
        [(p.location.coordinates[1], p.location.coordinates[0]) for p in matches],
    )
    return {"places": [format_place(p, eta) for p, eta in zip(matches, etas)]}
