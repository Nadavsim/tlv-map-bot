import asyncio
import os
import pandas as pd
from dotenv import load_dotenv
# NEW: We import async_sessionmaker instead of sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from models import Base, Place

# 1. Load environment variables
load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# FIX 1: Explicitly check that the variable loaded properly to satisfy the linter
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is missing from your .env file!")

async def load_data():
    # 2. Connect to the PostGIS Database
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all) 
        await conn.run_sync(Base.metadata.create_all)
    
    # 3. Extract the data from your CSV
    print("Reading CSV file...")
    df = pd.read_csv('cleaned_places.csv')
    
    # FIX 2: Use the modern async_sessionmaker for perfect type safety
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        print("Transforming and Loading data...")
        
        for index, row in df.iterrows():
            
            point_wkt = f"POINT({row['Longitude']} {row['Latitude']})"
            
            ig_url = row.get('Instagram')
            if pd.isna(ig_url):
                ig_url = None
                
            place = Place(
                name=row['Name'],
                category=str(row['Category']).strip().lower(),
                instagram_url=ig_url,
                location=point_wkt
            )
            
            session.add(place)
        
        # 4. Commit
        await session.commit()
        print(f"✅ Success! Loaded {len(df)} places into the PostGIS database.")

if __name__ == "__main__":
    asyncio.run(load_data())