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

class ApprovedSetup(Base):
    __tablename__ = "approved_setups"
    
    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(String, index=True, unique=True)
    symbol = Column(String, default="XAUUSD")
    action = Column(String, default="BUY")
    probability = Column(Float, default=0.0)
    approved_at = Column(DateTime, default=func.now())
    notes = Column(String, default="Approved by Trader via RLHF")

class TradeJournal(Base):
    __tablename__ = "trade_journal"
    
    id = Column(Integer, primary_key=True, index=True)
    tiket = Column(Integer, index=True)
    timestamp = Column(DateTime, index=True, default=func.now())
    event_type = Column(String, index=True) # ENTRY, SL_MODIFY, EXIT
    harga = Column(Float)
    alasan = Column(String) # Alasan AI / Top 3 Feature Contributions
    chart_snapshot = Column(String) # JSON 50 M1 candles

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

from sqlalchemy import text

def get_db_size():
    with sync_engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM market_data_merged"))
        return result.scalar()

def get_db_date_range():
    with sync_engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT MIN(time), MAX(time) FROM market_data_merged"))
            row = result.fetchone()
            if row:
                return row[0], row[1]
            return None, None
        except:
            return None, None

def log_trade_record(action: str, volume: float, price: float, sl: float, tp: float, profit: float = 0.0, comment: str = ""):
    """Simpan catatan transaksi ke database (trade_logs)."""
    try:
        Base.metadata.create_all(sync_engine)
        import datetime
        with Session(sync_engine) as session:
            log_entry = TradeLog(
                time=datetime.datetime.now(),
                action=action,
                volume=volume,
                price=price,
                sl=sl,
                tp=tp,
                profit=profit,
                comment=comment
            )
            session.add(log_entry)
            session.commit()
    except Exception as e:
        print(f"Failed to log trade to DB: {e}")

def get_recent_trade_logs(limit: int = 100):
    """Ambil riwayat transaksi terbaru dari tabel trade_logs."""
    import pandas as pd
    try:
        Base.metadata.create_all(sync_engine)
        query = f"SELECT id, time, action, volume, price, sl, tp, profit, comment FROM trade_logs ORDER BY time DESC LIMIT {limit}"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty and 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
        return df
    except Exception as e:
        print(f"Failed to read trade logs from DB: {e}")
        return pd.DataFrame()

# ==========================================
# RLHF: APPROVED SETUPS HELPERS
# ==========================================
def save_approved_setup(setup_id: str, symbol: str = "XAUUSD", action: str = "BUY", probability: float = 0.0, notes: str = ""):
    """Simpan ID setup yang telah disetujui trader (Human-in-the-loop) ke approved_setups."""
    try:
        Base.metadata.create_all(sync_engine)
        import datetime
        with Session(sync_engine) as session:
            # Cek jika sudah ada
            existing = session.query(ApprovedSetup).filter(ApprovedSetup.setup_id == str(setup_id)).first()
            if not existing:
                setup = ApprovedSetup(
                    setup_id=str(setup_id),
                    symbol=str(symbol),
                    action=str(action),
                    probability=float(probability),
                    approved_at=datetime.datetime.now(),
                    notes=str(notes) if notes else "Approved by Trader via RLHF"
                )
                session.add(setup)
                session.commit()
                return True
        return False
    except Exception as e:
        print(f"Failed to save approved setup: {e}")
        return False

def get_approved_setup_ids():
    """Ambil himpunan ID setup yang telah di-approve manusia untuk pembobotan LightGBM."""
    try:
        Base.metadata.create_all(sync_engine)
        with Session(sync_engine) as session:
            rows = session.query(ApprovedSetup.setup_id).all()
            return {r[0] for r in rows}
    except Exception as e:
        print(f"Failed to get approved setup IDs: {e}")
        return set()

def get_all_approved_setups():
    """Ambil seluruh data approved setups dalam bentuk DataFrame."""
    import pandas as pd
    try:
        Base.metadata.create_all(sync_engine)
        query = "SELECT id, setup_id, symbol, action, probability, approved_at, notes FROM approved_setups ORDER BY approved_at DESC"
        return pd.read_sql(query, con=sync_engine)
    except Exception as e:
        print(f"Failed to query approved setups: {e}")
        return pd.DataFrame()

# ==========================================
# BLACK BOX: TRADE JOURNAL & XAI HELPERS
# ==========================================
def log_trade_journal(tiket: int, event_type: str, harga: float, alasan: str, chart_snapshot: str):
    """
    Catat event transaksi (ENTRY, SL_MODIFY, EXIT) beserta 50 candle M1 snapshot dan alasan AI.
    """
    try:
        Base.metadata.create_all(sync_engine)
        import datetime
        with Session(sync_engine) as session:
            entry = TradeJournal(
                tiket=int(tiket),
                timestamp=datetime.datetime.now(),
                event_type=str(event_type),
                harga=float(harga),
                alasan=str(alasan),
                chart_snapshot=str(chart_snapshot)
            )
            session.add(entry)
            session.commit()
            return True
    except Exception as e:
        print(f"Failed to log trade journal: {e}")
        return False

def get_trade_journal_entries(limit: int = 100):
    """Ambil catatan trade_journal terbaru untuk analisis Black Box."""
    import pandas as pd
    try:
        Base.metadata.create_all(sync_engine)
        query = f"SELECT id, tiket, timestamp, event_type, harga, alasan, chart_snapshot FROM trade_journal ORDER BY timestamp DESC LIMIT {limit}"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty and 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        print(f"Failed to read trade journal: {e}")
        return pd.DataFrame()
