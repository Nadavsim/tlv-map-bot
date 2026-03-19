import os
import difflib
import random
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
        # Unpack the location AND the timestamp
        user_lat, user_lon, pin_time = user_sessions[From]
        
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
                
                for index, place in enumerate(top_places, start=1):
                    name = place.name
                    ig_val = place.instagram_url
                    distance_meters = int(place.distance)
                    
                    walk_time = max(1, round(distance_meters / 80))
                    gmaps_url = f"https://www.google.com/maps/dir/?api=1&destination={place.lat},{place.lon}"
                    
                    ig_url = ""
                    if isinstance(ig_val, str) and ig_val.strip():
                        ig_url = f"\n📱 Insta: {ig_val}"
                        
                    cat_label = f" ({place.category.title()})" if is_surprise else ""
                    
                    speeds = {"walking": 80, "driving": 300, "transit": 200}
                    current_mode = user_sessions[From][3]
                    speed = speeds.get(current_mode, 80)

                    travel_time = max(1, round(distance_meters / speed))
                    mode_emoji = "🚶‍♂️" if current_mode == "walking" else "🚗" if current_mode == "driving" else "🚌"
                    reply_text += (
                        f"{index}. *{name}*{cat_label}\n"
                        f"📏 Distance: {distance_meters}m\n"
                        f"{mode_emoji} {current_mode.title()}: ~{travel_time} min\n"
                        f"🗺️ Navigate: {gmaps_url}{ig_url}\n\n"
                    )
                    
                resp.message(reply_text.strip())
            else:
                resp.message("Oops, something went wrong fetching the locations.")
    else:
        resp.message("👋 Welcome to your map bot! Please send me a WhatsApp Location Pin first.")

    return Response(content=str(resp), media_type="application/xml")