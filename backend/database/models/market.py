from sqlalchemy import Column, Integer, String, Float, DateTime
from ..connection import Base

class MarketData(Base):
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, index=True)
    time = Column(DateTime, index=True, unique=True)
    symbol = Column(String, index=True)
    timeframe = Column(String, index=True) # M1, M5, M15
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    tick_volume = Column(Integer)
    spread = Column(Integer)
    minutes_to_high_impact_news = Column(Float, default=9999) # Fitur makroekonomi
