from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import llm

load_dotenv()

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.ensure_indexes()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class ChatRequest(BaseModel):
    message: str
    lat: float
    lon: float


def format_place(place: dict) -> dict:
    distance_km = place["distance"] / 1000
    distance_str = f"{distance_km:.2f} km" if distance_km < 1 else f"{distance_km:.1f} km"

    lon, lat = place["location"]["coordinates"]
    maps_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"

    return {
        "name": place["name"],
        "category": place["category"],
        "distance": distance_str,
        "instagram_url": place.get("instagram_url"),
        "maps_url": maps_url,
    }


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/categories")
async def categories():
    return {"categories": await db.get_categories()}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    known_categories = await db.get_categories()
    if not known_categories:
        return {
            "reply": "The places database is empty. Run sync_places.py to load places from the map first.",
            "places": [],
        }

    extraction = llm.parse_food_request(req.message, known_categories)

    if not extraction["category"]:
        return {
            "reply": extraction["clarifying_question"]
            or "Not sure what you're craving - can you tell me a type of food?",
            "places": [],
        }

    matches = await db.find_nearest(extraction["category"], req.lat, req.lon, limit=3)
    if not matches:
        return {
            "reply": f"I don't have any {extraction['category']} spots saved yet.",
            "places": [],
        }

    return {
        "reply": f"Here are the closest {extraction['category']} spots:",
        "places": [format_place(p) for p in matches],
    }
