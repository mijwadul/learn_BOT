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

class RejectedSetup(Base):
    __tablename__ = "rejected_setups"
    
    id = Column(Integer, primary_key=True, index=True)
    setup_id = Column(String, index=True, unique=True)
    symbol = Column(String, default="XAUUSD")
    action = Column(String, default="BUY")
    probability = Column(Float, default=0.0)
    rejected_at = Column(DateTime, default=func.now())
    notes = Column(String, default="Rejected by Trader via RLHF")

class TradeJournal(Base):
    __tablename__ = "trade_journal"
    
    id = Column(Integer, primary_key=True, index=True)
    tiket = Column(Integer, index=True)
    timestamp = Column(DateTime, index=True, default=func.now())
    event_type = Column(String, index=True) # ENTRY, SL_MODIFY, EXIT
    harga = Column(Float)
    alasan = Column(String) # Alasan AI / Top 3 Feature Contributions
    chart_snapshot = Column(String) # JSON 50 M1 candles

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

def get_historical_pnl_feedback():
    """Ambil riwayat transaksi lengkap untuk PnL Feedback Loop pada AI Researcher."""
    import pandas as pd
    try:
        Base.metadata.create_all(sync_engine)
        # Ambil max 10000 trade terakhir
        query = "SELECT time, profit, action FROM trade_logs WHERE action IN ('BUY', 'SELL') ORDER BY time DESC LIMIT 10000"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty and 'time' in df.columns:
            df['time'] = pd.to_datetime(df['time'])
        return df
    except Exception as e:
        print(f"Failed to fetch historical PnL feedback: {e}")
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

def save_rejected_setup(setup_id: str, symbol: str = "XAUUSD", action: str = "BUY", probability: float = 0.0, notes: str = ""):
    """Simpan ID setup yang telah ditolak trader (Human-in-the-loop) ke rejected_setups."""
    try:
        Base.metadata.create_all(sync_engine)
        import datetime
        with Session(sync_engine) as session:
            existing = session.query(RejectedSetup).filter(RejectedSetup.setup_id == str(setup_id)).first()
            if not existing:
                setup = RejectedSetup(
                    setup_id=str(setup_id),
                    symbol=str(symbol),
                    action=str(action),
                    probability=float(probability),
                    rejected_at=datetime.datetime.now(),
                    notes=str(notes) if notes else "Rejected by Trader via RLHF"
                )
                session.add(setup)
                session.commit()
                return True
        return False
    except Exception as e:
        print(f"Failed to save rejected setup: {e}")
        return False

def get_rejected_setup_ids():
    """Ambil himpunan ID setup yang telah di-reject manusia untuk penalty LightGBM."""
    try:
        Base.metadata.create_all(sync_engine)
        with Session(sync_engine) as session:
            rows = session.query(RejectedSetup.setup_id).all()
            return {r[0] for r in rows}
    except Exception as e:
        print(f"Failed to get rejected setup IDs: {e}")
        return set()

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

# ==========================================
# MACRO DATA: ECONOMIC CALENDAR CACHE
# ==========================================
def save_macro_data(events_df):
    """Simpan data jadwal kalender ekonomi ke database untuk cache."""
    try:
        Base.metadata.create_all(sync_engine)
        import pandas as pd
        if events_df.empty:
            return 0
            
        with Session(sync_engine) as session:
            count = 0
            for _, row in events_df.iterrows():
                event_id_val = f"{row['date']}_{row['event']}"
                
                # Check if exists to update actual if needed
                existing = session.query(EconomicEvent).filter(EconomicEvent.event_id == event_id_val).first()
                if existing:
                    # Update if actual is now available
                    if pd.notna(row.get('actual')) and existing.actual is None:
                        existing.actual = float(row['actual'])
                        if pd.notna(row.get('change')):
                            existing.change = float(row['change'])
                else:
                    new_event = EconomicEvent(
                        event_id=event_id_val,
                        date=row['date'],
                        country=row.get('country', ''),
                        event_name=row.get('event', ''),
                        currency=row.get('currency', ''),
                        estimate=float(row['estimate']) if pd.notna(row.get('estimate')) else None,
                        previous=float(row['previous']) if pd.notna(row.get('previous')) else None,
                        actual=float(row['actual']) if pd.notna(row.get('actual')) else None,
                        change=float(row['change']) if pd.notna(row.get('change')) else None,
                        impact=row.get('impact', '')
                    )
                    session.add(new_event)
                    count += 1
                    
            session.commit()
            return count
    except Exception as e:
        print(f"Failed to save macro data to DB: {e}")
        return 0

def get_macro_data(start_date: str, end_date: str):
    """Ambil data kalender ekonomi dari cache database."""
    import pandas as pd
    try:
        Base.metadata.create_all(sync_engine)
        query = f"SELECT * FROM economic_events WHERE date >= '{start_date}' AND date <= '{end_date}' ORDER BY date ASC"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], utc=True)
        return df
    except Exception as e:
        print(f"Failed to read macro data from DB: {e}")
        return pd.DataFrame()
