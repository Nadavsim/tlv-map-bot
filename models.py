import os
import asyncio
from dotenv import load_dotenv
from sqlalchemy import Column, Integer, String, text
from geoalchemy2 import Geometry
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine

# Load environment variables
load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# This creates a base class that our table models will inherit from
Base = declarative_base()

class Place(Base):
    __tablename__ = 'places'
    
    # Standard columns
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, index=True, nullable=False)
    instagram_url = Column(String, nullable=True)
    
    # The magic spatial column! 
    # SRID 4326 is the standard GPS coordinate system (WGS 84)
    location = Column(Geometry(geometry_type='POINT', srid=4326))

# --- DATABASE EXECUTION BLOCK ---
# Create the async engine using your Azure URL
engine = create_async_engine(DATABASE_URL, echo=False)

async def init_db():
    async with engine.begin() as conn:
        print("Enabling PostGIS on Azure...")
        # Tell Azure to install PostGIS into this specific database
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        
        print("Creating the places table...")
        # Create the tables
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables successfully built in the cloud!")

if __name__ == "__main__":
    asyncio.run(init_db())