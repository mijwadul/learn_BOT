from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from config import Config

engine = create_async_engine(Config.DATABASE_URL, echo=False)
sync_engine = create_engine(Config.SYNC_DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()
