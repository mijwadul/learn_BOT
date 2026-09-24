from sqlalchemy import Column, Integer, String, Float, DateTime
from ..connection import Base

class EconomicEvent(Base):
    __tablename__ = "economic_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, index=True, unique=True)
    date = Column(DateTime, index=True)
    country = Column(String)
    event_name = Column(String)
    currency = Column(String)
    estimate = Column(Float, nullable=True)
    previous = Column(Float, nullable=True)
    actual = Column(Float, nullable=True)
    change = Column(Float, nullable=True)
    impact = Column(String)
