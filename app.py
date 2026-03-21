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

# ==========================================
# 1. CONFIGURATION & SETUP
# ==========================================
load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL", "")
gmaps_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# APIs
gmaps = googlemaps.Client(key=gmaps_key) if gmaps_key else None
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI()

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
    # BLOCK 0: THE ESCAPE HATCH (Reset)
    # ==========================================
    if incoming_msg in ["reset", "restart", "clear"]:
        if From in user_sessions:
            del user_sessions[From] # Wipe their memory
        resp.message("🔄 Memory wiped! Please send me a fresh Location Pin to start over.")
        return Response(content=str(resp), media_type="application/xml")

    # ==========================================
    # BLOCK 1: GREETINGS & INTRO (No location needed)
    # ==========================================
    greetings = ["hi", "hello", "hey", "start", ".", "היי", "שלום"]
    if incoming_msg in greetings:
        # If they type reset, wipe their location memory so they aren't stuck!
        if incoming_msg in ["reset", "restart"] and From in user_sessions:
            del user_sessions[From]
            
        intro_text = (
            "👋 *Welcome to TLV-bot!*\n\n"
            "I can help you find the best spots in Tel Aviv right from your phone.\n\n"
            "👇 *Here is how to use me:*\n"
            "1️⃣ *Send Location:* Tap the 📎 icon, select 'Location', and send your pin.\n"
            "2️⃣ *Search:* Tell me what you want (e.g., 'Coffee', 'Wine bar').\n"
            "3️⃣ *Travel Mode:* Reply 'drive', 'walk', or 'bus'.\n"
            "4️⃣ *Restart:* Type 'reset' at any time to start over.\n\n"
            "📍 *Send me your location pin to get started!*"
        )
        resp.message(intro_text)
        return Response(content=str(resp), media_type="application/xml")

    # ==========================================
    # BLOCK 2: USER SENDS A LOCATION PIN
    # ==========================================
    if Latitude and Longitude:
        # Save the new location, timestamp, and default mode to memory
        user_sessions[From] = (float(Latitude), float(Longitude), datetime.now(), "walking")
        
        # Fetch 3 random categories to suggest
        async with async_session() as session:
            cat_result = await session.execute(select(Place.category).distinct())
            categories = [row[0] for row in cat_result.all()]
            
            suggestion_text = "Coffee, Pizza, etc."
            if len(categories) >= 3:
                suggestions = random.sample(categories, 3)
                suggestion_text = f"{suggestions[0].title()}, {suggestions[1].title()}, or {suggestions[2].title()}"
                
        resp.message(f"📍 Location locked! What are you looking for? (e.g., {suggestion_text}, or type 'Surprise Me')")
        return Response(content=str(resp), media_type="application/xml")

    # ==========================================
    # BLOCK 3: SESSION VALIDATION
    # ==========================================
    if From not in user_sessions:
        resp.message("👋 Please send me a WhatsApp Location Pin first so I know where you are!")
        return Response(content=str(resp), media_type="application/xml")

    # Unpack the user's data
    session_data = user_sessions[From]
    user_lat, user_lon, pin_time, current_mode = session_data if len(session_data) > 3 else (*session_data, "walking")

    # Check expiration (3 hours)
    if datetime.now() - pin_time > timedelta(hours=3):
        del user_sessions[From]
        resp.message("⏳ It's been a while! Please send a fresh location pin so I can find what's nearby.")
        return Response(content=str(resp), media_type="application/xml")

    # ==========================================
    # BLOCK 4: UPDATE TRAVEL MODE
    # ==========================================
    mode_map = {
        "walk": "walking", "walking": "walking",
        "drive": "driving", "driving": "driving", "car": "driving",
        "bus": "transit", "transit": "transit", "train": "transit"
    }
    if incoming_msg in mode_map:
        new_mode = mode_map[incoming_msg]
        user_sessions[From] = (user_lat, user_lon, pin_time, new_mode)
        resp.message(f"🚗 Travel mode updated to: *{new_mode.title()}*\nNow tell me what you want to find!")
        return Response(content=str(resp), media_type="application/xml")

    # ==========================================
    # BLOCK 5: DATABASE SEARCH & MAPS ROUTING
    # ==========================================
    async with async_session() as session:
        cat_result = await session.execute(select(Place.category).distinct())
        valid_categories = [row[0] for row in cat_result.all()]
        
        # Help Menu
        help_keywords = ["help", "menu", "options", "categories", "list"]
        if incoming_msg in help_keywords:
            cat_list = "\n".join([f"🔸 {c.title()}" for c in sorted(valid_categories)])
            resp.message(f"Here is everything I can find for you right now:\n\n{cat_list}\n\nJust reply with any of these, or 'Surprise Me'!")
            return Response(content=str(resp), media_type="application/xml")
        
        # Surprise Logic vs Specific Search
        surprise_keywords = ["surprise", "surprise me", "any", "nearest", "anything"]
        is_surprise = len(difflib.get_close_matches(incoming_msg, surprise_keywords, n=1, cutoff=0.6)) > 0
        
        user_point = f"POINT({user_lon} {user_lat})"
        distance_calc = func.ST_DistanceSphere(Place.location, func.ST_GeomFromText(user_point, 4326)).label("distance")
        
        stmt = select(
            Place.name, Place.category, Place.instagram_url,
            func.ST_Y(Place.location).label("lat"), func.ST_X(Place.location).label("lon"), distance_calc
        )

        if is_surprise:
            stmt = stmt.order_by(distance_calc).limit(3)
        else:
            matches = difflib.get_close_matches(incoming_msg, valid_categories, n=1, cutoff=0.6)
            if not matches:
                resp.message(f"I couldn't find '{incoming_msg}'. Try typing 'Menu' to see what I have, or 'Surprise Me'!")
                return Response(content=str(resp), media_type="application/xml")
                
            best_category = matches[0]
            stmt = stmt.where(Place.category == best_category).order_by(distance_calc).limit(3)

        # Execute PostGIS Query
        result = await session.execute(stmt)
        top_places = result.all()

        if top_places:
            reply_text = f"🎲 Surprise! Top {len(top_places)} closest spots:\n\n" if is_surprise else f"Here are the top {len(top_places)} nearest {best_category.title()} spots:\n\n"
            if not is_surprise and incoming_msg != best_category:
                reply_text = f"(Assuming you meant '{best_category.title()}'...) \n\n" + reply_text
            
            # Google Maps Distance Matrix
            destinations = [f"{p.lat},{p.lon}" for p in top_places]
            durations = ["N/A"] * len(top_places)
            
            if gmaps:
                try:
                    gmaps_client = cast(Any, gmaps)
                    matrix = gmaps_client.distance_matrix(origins=f"{user_lat},{user_lon}", destinations=destinations, mode=current_mode, units="metric")
                    for i, el in enumerate(matrix['rows'][0]['elements']):
                        if el['status'] == 'OK':
                            durations[i] = el['duration']['text']
                        else:
                            # If Google rejects the route, show the API status (e.g., ZERO_RESULTS)
                            durations[i] = f"Route Error: {el['status']}"
                except Exception as e:
                    # If the API call fails entirely, print the Python error
                    durations = [f"API Error: {str(e)[:25]}"] * len(top_places)
            else:
                durations = ["Missing API Key"] * len(top_places)

            # Build Final Output
            for index, place in enumerate(top_places, start=1):
                mode_emoji = "🚗" if current_mode == "driving" else "🚌" if current_mode == "transit" else "🚶‍♂️"
                
                # --- UPGRADED: Dynamic Google Maps Directions Link ---
                gmaps_url = f"https://www.google.com/maps/dir/?api=1&origin={user_lat},{user_lon}&destination={place.lat},{place.lon}&travelmode={current_mode}"
                
                ig_url = f"\n📱 Insta: {place.instagram_url}" if isinstance(place.instagram_url, str) and place.instagram_url.strip() else ""
                cat_label = f" ({place.category.title()})" if is_surprise else ""
                
                reply_text += (
                    f"{index}. *{place.name}*{cat_label}\n"
                    f"📏 Distance: {int(place.distance)}m\n"
                    f"{mode_emoji} {current_mode.title()}: {durations[index - 1]}\n"
                    f"🗺️ Navigate: {gmaps_url}{ig_url}\n\n"
                )
                
            reply_text += "💡 *Tip:* Reply 'drive' or 'walk' to change mode, or 'reset' to start over!"
            resp.message(reply_text.strip())
        else:
            resp.message("Oops, something went wrong fetching the locations.")

    return Response(content=str(resp), media_type="application/xml")