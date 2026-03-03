import os
import difflib
from fastapi import FastAPI, Form, Response
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

# NEW: Import SQLAlchemy tools and your database model
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from models import Place

# 1. Load environment variables securely (with linter fallbacks)
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

    # Logic: Did the user send a location pin?
    if Latitude and Longitude:
        user_sessions[From] = (float(Latitude), float(Longitude))
        resp.message("📍 Location locked! What are you looking for? (e.g., Coffee, Pizza)")
        return Response(content=str(resp), media_type="application/xml")

    # Logic: Did the user type a category?
    if From in user_sessions:
        user_lat, user_lon = user_sessions[From]
        
        # Open a connection to PostGIS
        async with async_session() as session:
            
            # --- FEATURE 1: TYPO HANDLING ---
            # Query the database for all unique categories
            cat_result = await session.execute(select(Place.category).distinct())
            valid_categories = [row[0] for row in cat_result.all()]
            
            matches = difflib.get_close_matches(incoming_msg, valid_categories, n=1, cutoff=0.6)
            
            if not matches:
                resp.message(f"I couldn't find any places for '{incoming_msg}'. Try another category!")
                return Response(content=str(resp), media_type="application/xml")
                
            best_category = matches[0]

            # --- FEATURE 2: POSTGIS SPATIAL QUERY ---
            # Create a string representation of the user's location (Longitude first!)
            user_point = f"POINT({user_lon} {user_lat})"
            
            # Tell PostGIS to calculate the distance on the curve of the Earth
            distance_calc = func.ST_DistanceSphere(
                Place.location, 
                func.ST_GeomFromText(user_point, 4326)
            ).label("distance")
            
            # Build the hyper-optimized SQL query
            stmt = (
                select(
                    Place.name,
                    Place.instagram_url,
                    func.ST_Y(Place.location).label("lat"), # Extract Latitude
                    func.ST_X(Place.location).label("lon"), # Extract Longitude
                    distance_calc
                )
                .where(Place.category == best_category)
                .order_by(distance_calc) # Order by closest distance
                .limit(1) # Only return the absolute closest one
            )
            
            # Execute the query and grab the first row
            result = await session.execute(stmt)
            closest_place = result.first()

            if closest_place:
                name = closest_place.name
                ig_val = closest_place.instagram_url
                distance_meters = int(closest_place.distance)
                
                # --- FEATURE 3: DYNAMIC LINKS ---
                gmaps_url = f"https://www.google.com/maps/dir/?api=1&destination={closest_place.lat},{closest_place.lon}"
                
                ig_url = ""
                if isinstance(ig_val, str) and ig_val.strip():
                    ig_url = f"\n📱 Instagram: {ig_val}"
                
                reply_text = (
                    f"Your nearest {best_category.title()} is *{name}*!\n"
                    f"🚶‍♂️ Distance: {distance_meters} meters away.\n"
                    f"🗺️ Navigate: {gmaps_url}{ig_url}"
                )
                
                if incoming_msg != best_category:
                    reply_text = f"(Assuming you meant '{best_category.title()}'...) \n\n" + reply_text
                    
                resp.message(reply_text)
            else:
                resp.message("Oops, something went wrong fetching the location.")
    else:
        resp.message("👋 Welcome to your map bot! Please send me a WhatsApp Location Pin first.")

    return Response(content=str(resp), media_type="application/xml")