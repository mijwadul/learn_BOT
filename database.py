from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy import Column, Integer, String, Float, DateTime, select, func
from config import Config

engine = create_async_engine(Config.DATABASE_URL, echo=False)
sync_engine = create_engine(Config.SYNC_DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

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

class TradeLog(Base):
    __tablename__ = "trade_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    time = Column(DateTime, index=True)
    action = Column(String) # BUY, SELL, PARTIAL_CLOSE, CLOSE
    volume = Column(Float)
    price = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    profit = Column(Float)
    comment = Column(String)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

def get_db_size():
    with Session(sync_engine) as session:
        return session.query(func.count(MarketData.id)).scalar()
