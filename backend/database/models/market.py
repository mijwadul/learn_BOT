from sqlalchemy import Column, Integer, String, Float, DateTime, BigInteger, UniqueConstraint
from ..connection import Base

class MarketData(Base):
    __tablename__ = "market_data"
    __table_args__ = (UniqueConstraint('time', 'symbol', name='uq_market_data_time_symbol'),)
    
    id = Column(Integer, primary_key=True, index=True)
    time = Column(DateTime, index=True)
    symbol = Column(String(20), index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    tick_volume = Column(BigInteger, default=0)
    
    # BBMA Core Indicators
    sma_20 = Column(Float)       # Mid BB
    bb_upper = Column(Float)     # Upper BB
    bb_lower = Column(Float)     # Lower BB
    ema_50 = Column(Float)       # EMA 50
    
    # 4 Garis Terpisah LWMA
    lwma_5_high = Column(Float)  # LWMA 5 High
    lwma_10_high = Column(Float) # LWMA 10 High
    lwma_5_low = Column(Float)   # LWMA 5 Low
    lwma_10_low = Column(Float)  # LWMA 10 Low
