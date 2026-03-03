from sqlalchemy import Column, Integer, String
from geoalchemy2 import Geometry
from sqlalchemy.orm import declarative_base

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