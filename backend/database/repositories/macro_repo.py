import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from ..connection import sync_engine, Base
from ..models.macro import EconomicEvent

def save_macro_data(events_df):
    """Simpan data jadwal kalender ekonomi ke database untuk cache."""
    try:
        Base.metadata.create_all(sync_engine)
        if events_df.empty:
            return 0
            
        with Session(sync_engine) as session:
            count = 0
            for _, row in events_df.iterrows():
                event_id_val = f"{row['date']}_{row['event']}"
                
                existing = session.query(EconomicEvent).filter(EconomicEvent.event_id == event_id_val).first()
                if existing:
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
        logging.error(f"Failed to save macro data to DB: {e}")
        return 0

def get_macro_data(start_date: str, end_date: str):
    """Ambil data kalender ekonomi dari cache database."""
    try:
        Base.metadata.create_all(sync_engine)
        query = f"SELECT * FROM economic_events WHERE date >= '{start_date}' AND date <= '{end_date}' ORDER BY date ASC"
        df = pd.read_sql(query, con=sync_engine)
        if not df.empty and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], utc=True)
        return df
    except Exception as e:
        logging.error(f"Failed to read macro data from DB: {e}")
        return pd.DataFrame()

def get_next_high_impact_event():
    """
    Mengambil 1 economic event 'High Impact' terdekat yang akan datang (atau baru saja rilis < 15 menit).
    Digunakan untuk countdown dan proteksi volatilitas di antarmuka UI.
    """
    try:
        Base.metadata.create_all(sync_engine)
        now_utc = datetime.now(timezone.utc)
        lookback_limit = (now_utc - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        lookforward_limit = (now_utc + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        
        with Session(sync_engine) as session:
            events = session.query(EconomicEvent).filter(
                EconomicEvent.date >= lookback_limit,
                EconomicEvent.date <= lookforward_limit
            ).order_by(EconomicEvent.date.asc()).all()
            
            for ev in events:
                imp = str(ev.impact).lower() if ev.impact else ""
                if 'high' in imp or imp == '3' or 'red' in imp:
                    ev_date = ev.date
                    if ev_date.tzinfo is None:
                        ev_date = ev_date.replace(tzinfo=timezone.utc)
                    diff_seconds = (ev_date - now_utc).total_seconds()
                    
                    return {
                        "id": ev.id,
                        "event_id": ev.event_id,
                        "event_name": ev.event_name,
                        "country": ev.country,
                        "currency": ev.currency,
                        "impact": ev.impact,
                        "date": ev_date.isoformat(),
                        "estimate": ev.estimate,
                        "previous": ev.previous,
                        "actual": ev.actual,
                        "seconds_remaining": int(diff_seconds),
                        "minutes_remaining": round(diff_seconds / 60.0, 1),
                        "is_imminent": 0 <= diff_seconds <= 1800
                    }
        return None
    except Exception as e:
        logging.debug(f"Gagal mengambil next high impact event: {e}")
        return None

def get_upcoming_economic_events(limit: int = 10):
    """Mengambil daftar event ekonomi mendatang hingga limit tertentu."""
    try:
        Base.metadata.create_all(sync_engine)
        now_utc = datetime.now(timezone.utc)
        lookback_limit = (now_utc - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S')
        lookforward_limit = (now_utc + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        
        with Session(sync_engine) as session:
            events = session.query(EconomicEvent).filter(
                EconomicEvent.date >= lookback_limit,
                EconomicEvent.date <= lookforward_limit
            ).order_by(EconomicEvent.date.asc()).limit(limit).all()
            
            result = []
            for ev in events:
                ev_date = ev.date
                if ev_date.tzinfo is None:
                    ev_date = ev_date.replace(tzinfo=timezone.utc)
                diff_seconds = (ev_date - now_utc).total_seconds()
                result.append({
                    "id": ev.id,
                    "event_name": ev.event_name,
                    "country": ev.country,
                    "currency": ev.currency,
                    "impact": ev.impact,
                    "date": ev_date.isoformat(),
                    "estimate": ev.estimate,
                    "previous": ev.previous,
                    "actual": ev.actual,
                    "seconds_remaining": int(diff_seconds),
                    "minutes_remaining": round(diff_seconds / 60.0, 1)
                })
            return result
    except Exception as e:
        logging.debug(f"Gagal mengambil upcoming economic events: {e}")
        return []
