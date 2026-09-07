import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db
from .models import PlaceResult
from .services import llm, location, routing

load_dotenv()

# .parent.parent, not .parent: this file lives in backend/, but static/ (built
# by frontend/'s Vite build) sits at the repo root, a sibling of backend/.
BASE_DIR = Path(__file__).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.ensure_indexes()
    yield


app = FastAPI(lifespan=lifespan)
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


@app.post("/api/resolve-location")
async def resolve_location(req: LocationLinkRequest):
    coords = await asyncio.to_thread(location.resolve_maps_link, req.text.strip())
    if not coords:
        return {"lat": None, "lon": None}
    lat, lon = coords
    return {"lat": lat, "lon": lon}


@app.get("/api/categories")
async def categories():
    return {"categories": await db.get_categories()}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    known_categories = await db.get_categories()
    if not known_categories:
        return {
            "reply": "The places database is empty. Run `python -m scripts.sync_places` to load places first.",
            "places": [],
        }

    extraction = await llm.parse_food_request(req.message, known_categories)

    if not extraction["any_category"] and not extraction["category"]:
        return {
            "reply": extraction["clarifying_question"]
            or "Not sure what you're craving - can you tell me a type of food?",
            "places": [],
        }

    category = extraction["category"]
    matches = await db.find_nearest(category, req.lat, req.lon, limit=3)
    if not matches:
        label = category or "any"
        return {
            "reply": f"I don't have any {label} spots saved yet.",
            "places": [],
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
    }
