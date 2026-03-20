import os
import difflib
import random
import googlemaps
from typing import Any, cast
from datetime import datetime, timedelta
from fastapi import FastAPI, Form, Response
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from models import Place

# 1. Load environment variables
load_dotenv()
twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
gmaps_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
gmaps = googlemaps.Client(key=gmaps_key) if gmaps_key else None

app = FastAPI()

# 2. Setup the async database engine
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

# Temporary memory for user locations
user_sessions = {}

@app.post("/whatsapp")
async def whatsapp_reply(
    Body: str = Form(""), 
    Latitude: str = Form(None), 
    Longitude: str = Form(None),
    From: str = Form(...) 
):
    incoming_msg = Body.strip().lower()
    resp = MessagingResponse()

    # ==========================================
    # LOGIC 1: USER SENDS A LOCATION PIN
    # ==========================================
    if Latitude and Longitude:
        # --- FEATURE 2: SMART PIN EXPIRATION (Saving the timestamp) ---
        user_sessions[From] = (float(Latitude), float(Longitude), datetime.now(), "walking")
        mode_map = {
                    "walk": "walking",
                    "drive": "driving",
                    "bus": "transit",
                    "train": "transit"
                }
        
        if incoming_msg in mode_map:
            lat, lon, time, _ = user_sessions[From]
            new_mode = mode_map[incoming_msg]
            user_sessions[From] = (lat, lon, time, new_mode)
            resp.message(f"🚗 Travel mode updated to: *{new_mode.title()}*")
            return Response(content=str(resp), media_type="application/xml")
        
        async with async_session() as session:
            # --- FEATURE 3: DYNAMIC WELCOME MESSAGE ---
            # Grab all categories to randomly suggest 3 of them
            cat_result = await session.execute(select(Place.category).distinct())
            categories = [row[0] for row in cat_result.all()]
            
            if len(categories) >= 3:
                suggestions = random.sample(categories, 3)
                suggestion_text = f"{suggestions[0].title()}, {suggestions[1].title()}, or {suggestions[2].title()}"
            else:
                suggestion_text = "Coffee, Pizza, etc."
                
        resp.message(f"📍 Location locked! What are you looking for? (e.g., {suggestion_text}, or type 'Surprise Me')")
        return Response(content=str(resp), media_type="application/xml")

    # ==========================================
    # LOGIC 2: USER SENDS A TEXT MESSAGE
    # ==========================================
    if From in user_sessions:
        # Unpack location, timestamp, and optional travel mode
        session_data = user_sessions[From]
        if len(session_data) > 3:
            user_lat, user_lon, pin_time, current_mode = session_data
        else:
            user_lat, user_lon, pin_time = session_data
            current_mode = "walking"
        
        # --- FEATURE 2 (Cont.): ENFORCING THE EXPIRATION (3 HOURS) ---
        if datetime.now() - pin_time > timedelta(hours=3):
            del user_sessions[From] # Clear their memory
            resp.message("⏳ It's been a while! Please send a fresh location pin so I can find what's nearby.")
            return Response(content=str(resp), media_type="application/xml")
        
        async with async_session() as session:
            # Fetch valid categories for our matching logic
            cat_result = await session.execute(select(Place.category).distinct())
            valid_categories = [row[0] for row in cat_result.all()]
            
            # --- FEATURE 1: THE HELP / MENU COMMAND ---
            help_keywords = ["help", "menu", "options", "categories", "list"]
            if incoming_msg in help_keywords:
                cat_list = "\n".join([f"🔸 {c.title()}" for c in sorted(valid_categories)])
                resp.message(f"Here is everything I can find for you right now:\n\n{cat_list}\n\nJust reply with any of these, or 'Surprise Me'!")
                return Response(content=str(resp), media_type="application/xml")
            
            # --- EXISTING FEATURE: "SURPRISE ME" LOGIC ---
            surprise_keywords = ["surprise", "surprise me", "any", "nearest", "anything"]
            surprise_matches = difflib.get_close_matches(incoming_msg, surprise_keywords, n=1, cutoff=0.6)
            is_surprise = len(surprise_matches) > 0
            
            # Start building the base SQL query
            user_point = f"POINT({user_lon} {user_lat})"
            distance_calc = func.ST_DistanceSphere(
                Place.location, 
                func.ST_GeomFromText(user_point, 4326)
            ).label("distance")
            
            stmt = select(
                Place.name,
                Place.category, 
                Place.instagram_url,
                func.ST_Y(Place.location).label("lat"), 
                func.ST_X(Place.location).label("lon"), 
                distance_calc
            )

            if is_surprise:
                stmt = stmt.order_by(distance_calc).limit(3)
            else:
                # --- EXISTING FEATURE: TYPO HANDLING ---
                matches = difflib.get_close_matches(incoming_msg, valid_categories, n=1, cutoff=0.6)
                
                if not matches:
                    resp.message(f"I couldn't find '{incoming_msg}'. Try typing 'Menu' to see what I have, or 'Surprise Me'!")
                    return Response(content=str(resp), media_type="application/xml")
                    
                best_category = matches[0]
                stmt = stmt.where(Place.category == best_category).order_by(distance_calc).limit(3)

            # --- EXECUTE THE POSTGIS QUERY ---
            result = await session.execute(stmt)
            top_places = result.all()

            if top_places:
                if is_surprise:
                    reply_text = f"🎲 Surprise! Here are the {len(top_places)} absolute closest spots to you right now:\n\n"
                else:
                    reply_text = f"Here are the top {len(top_places)} nearest {best_category.title()} spots:\n\n"
                    if incoming_msg != best_category:
                        reply_text = f"(Assuming you meant '{best_category.title()}'...) \n\n" + reply_text
                
                # --- NEW: BATCHED GOOGLE MAPS API CALL ---
                destinations = [f"{p.lat},{p.lon}" for p in top_places]
                
                durations = []
                if gmaps:
                    try:
                        gmaps_client = cast(Any, gmaps)
                        # Send 1 request for all 3 places
                        matrix = gmaps_client.distance_matrix(
                            origins=f"{user_lat},{user_lon}",
                            destinations=destinations,
                            mode=current_mode,
                            units="metric"
                        )
                        elements = matrix['rows'][0]['elements']
                        for el in elements:
                            if el['status'] == 'OK':
                                durations.append(el['duration']['text']) # e.g., "12 mins"
                            else:
                                durations.append("N/A")
                    except Exception as e:
                        durations = ["N/A"] * len(top_places)
                else:
                    durations = ["N/A"] * len(top_places)

                # --- BUILD THE FINAL MESSAGE ---
                for index, place in enumerate(top_places, start=1):
                    name = place.name
                    ig_val = place.instagram_url
                    distance_meters = int(place.distance)
                    travel_time_str = durations[index - 1]
                    
                    if current_mode == "driving":
                        mode_emoji = "🚗"
                    elif current_mode == "transit":
                        mode_emoji = "🚌"
                    else:
                        mode_emoji = "🚶‍♂️"
                        
                    gmaps_url = f"https://www.google.com/maps/dir/?api=1&destination={place.lat},{place.lon}"
                    
                    ig_url = ""
                    if isinstance(ig_val, str) and ig_val.strip():
                        ig_url = f"\n📱 Insta: {ig_val}"
                        
                    cat_label = f" ({place.category.title()})" if is_surprise else ""
                    
                    reply_text += (
                        f"{index}. *{name}*{cat_label}\n"
                        f"📏 Distance: {distance_meters}m\n"
                        f"{mode_emoji} {current_mode.title()}: {travel_time_str}\n"
                        f"🗺️ Navigate: {gmaps_url}{ig_url}\n\n"
                    )
                    
                resp.message(reply_text.strip())
            else:
                resp.message("Oops, something went wrong fetching the locations.")
    else:
        resp.message("👋 Welcome to your map bot! Please send me a WhatsApp Location Pin first.")

    return Response(content=str(resp), media_type="application/xml")