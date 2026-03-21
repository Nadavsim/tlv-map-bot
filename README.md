# 📍 Tel Aviv WhatsApp Map Bot (TLV-bot)

A location-aware WhatsApp bot built with Python and FastAPI that helps users instantly find the nearest coffee shops, restaurants, and points of interest in Tel Aviv. The bot uses a fully managed Azure PostGIS spatial database to perform native, blazing-fast coordinate distance calculations and integrates with the Google Maps API for real-time travel routing.

## ✨ Features
* **Live Location Processing:** Accepts WhatsApp location pins to set the user's current coordinates.
* **Geospatial Distance Math:** Uses PostGIS `ST_DistanceSphere` to natively calculate the exact shortest distance (in meters) to the requested category.
* **Smart Conversational Memory:** Remembers the user's location pin and preferred travel mode for up to 3 hours, allowing for rapid follow-up searches.
* **Dynamic Travel Modes:** Users can seamlessly switch between `walking`, `driving`, and `transit`. The bot queries the Google Maps Distance Matrix API to provide real-time ETAs.
* **Typo-Tolerance & NLP:** Implements fuzzy string matching (`difflib`) to automatically correct slightly misspelled categories (e.g., "cofee" -> "coffee") and handles natural language triggers like "Surprise Me".
* **Deep-Linked Navigation:** Automatically generates a formatted Google Maps URL that instantly opens the user's maps app with the destination and specific travel mode pre-loaded.
* **Social Integration:** Pulls associated Instagram profiles for the recommended spots.

## 🏗️ Cloud System Architecture
* **Cloud Hosting:** Azure App Service (Linux, Free Tier).
* **CI/CD Pipeline:** GitHub Actions (Automatic deployment on push to `main`).
* **Database:** Azure Database for PostgreSQL Flexible Server with the PostGIS extension enabled.
* **Backend Framework:** FastAPI (Python 3.11) running on Uvicorn.
* **ORM & Queries:** SQLAlchemy 2.0 (Asynchronous) / GeoAlchemy2.
* **External APIs:** Twilio API (WhatsApp Sandbox) and Google Maps API.

## 🚀 Setup & Deployment

### 1. Prerequisites
- Python 3.11+
- An Azure Account (For Database and App Service)
- A Twilio Account (Sandbox for WhatsApp)
- A Google Cloud Account (For Maps API Key)

### 2. Environment Variables
Create a `.env` file in the root directory and add the following keys:

```env
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
GOOGLE_MAPS_API_KEY=your_gmaps_api_key
# Ensure your Azure connection string ends with ?ssl=require
DATABASE_URL=postgresql+asyncpg://admin_user:password@your-db-server.postgres.database.azure.com:5432/postgres?ssl=require
```
### 3. Install Dependencies
Create a virtual environment and install the required packages:

```bash
python -m venv venv
venv\Scripts\activate  # On Windows
pip install -r requirements.txt
```

### 4. Initialize the Cloud Database
Run the setup script to explicitly enable the PostGIS extension on the Azure server and build the empty tables:

```bash
python models.py
```

### 5. Run the ETL Migration
Extract the location data from the CSV and load it into the PostGIS database:

```bash
python load_data.py
```

### 6. Clound Deployment
This project is configured for CI/CD via Azure App Service.

    1. Provision a Linux Web App in the Azure Portal.
    2. Add the four .env variables into the App Service Environment variables settings.
    3. Under Configuration, set the startup command to: python -m uvicorn app:app --host 0.0.0.0 --port 8000
    4. In the Deployment Center, link the repository to GitHub to trigger the automated build.
    5. Paste your final Azure App Service URL (e.g., https://your-app.azurewebsites.net/whatsapp) into your Twilio Sandbox Webhook settings.

### **Ready for the final push!**
Once you save this `README.md` and the completely reorganized `app.py` from earlier, run these three commands in your terminal to send everything up to the cloud:

```bash
git add .
git commit -m "Refactored code, added smart travel modes, and updated README for cloud architecture"
git push origin main
```
