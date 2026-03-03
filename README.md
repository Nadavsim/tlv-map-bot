# 📍 Tel Aviv WhatsApp Map Bot

A location-aware WhatsApp bot built with Python and FastAPI that helps users instantly find the nearest coffee shops, restaurants, and points of interest in Tel Aviv. The bot uses a PostGIS spatial database to perform native, blazing-fast coordinate distance calculations on the curve of the Earth.

## ✨ Features
* **Live Location Processing:** Accepts WhatsApp location pins to set the user's current coordinates.
* **Geospatial Distance Math:** Uses PostGIS `ST_DistanceSphere` to natively calculate the exact shortest distance (in meters) to the requested category.
* **Typo-Tolerance:** Implements fuzzy string matching (`difflib`) to automatically correct slightly misspelled categories (e.g., "cofee" -> "coffee").
* **Dynamic Navigation:** Automatically generates a clickable Google Maps routing link from the user's location to the destination.
* **Social Integration:** Pulls associated Instagram profiles for the recommended spots.

## 🏗️ System Architecture
* **Backend Framework:** FastAPI (Python) running on Uvicorn.
* **Database:** PostgreSQL with the PostGIS extension (running via Docker).
* **ORM & Queries:** SQLAlchemy 2.0 (Asynchronous).
* **Messaging API:** Twilio API for WhatsApp.
* **ETL Pipeline:** Pandas (used to extract, clean, and load initial CSV data into the database).
* **Local Tunneling:** ngrok.

## 🚀 Local Setup & Installation

### 1. Prerequisites
- Python 3.10+
- Docker Desktop (for the database)
- A Twilio Account (Sandbox for WhatsApp)
- ngrok

### 2. Environment Variables
Create a `.env` file in the root directory and add the following:

```env
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/tel_aviv_map
```

### 3. Start the Spatial Database
Make sure Docker is running, then spin up the PostGIS container:

```bash
docker-compose up -d
```

### 4. Install Dependencies
Create a virtual environment and install the required packages:

```bash
python -m venv venv
venv\Scripts\activate  # On Windows
pip install -r requirements.txt
```

### 5. Run the ETL Migration
Extract the location data from the CSV and load it into the PostGIS database:

```bash
python load_data.py
```

### 6. Run the Application
Start the FastAPI server:

```bash
uvicorn app:app --reload
```

Expose the local server to the internet using ngrok:

```bash
ngrok http 8000
```

Finally, paste your generated ngrok URL (appending `/whatsapp`) into your Twilio Sandbox Webhook settings.