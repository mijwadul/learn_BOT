import logging
import pandas as pd
from sqlalchemy import text
from ..connection import sync_engine

def get_db_size():
    with sync_engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM market_data_merged"))
            return result.scalar()
        except Exception:
            return 0

def get_db_date_range():
    with sync_engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT MIN(time), MAX(time) FROM market_data_merged"))
            row = result.fetchone()
            if row:
                return row[0], row[1]
            return None, None
        except Exception:
            return None, None

def fetch_historical_data_chunks(chunk_size=10000):
    """
    Mengambil data historis dalam potongan (chunks) dari tabel market_data_merged.
    ORDER BY dihapus dari query SQL untuk mencegah PostgreSQL lokal membuat file temp
    sementara yang menyebabkan crash (psycopg2.errors.UndefinedFile / pgsql_tmp).
    Pengurutan dilakukan di Python per-chunk setelah data diambil.
    """
    try:
        query = "SELECT * FROM market_data_merged"
        for chunk in pd.read_sql(query, con=sync_engine, chunksize=chunk_size):
            if not chunk.empty and 'time' in chunk.columns:
                chunk['time'] = pd.to_datetime(chunk['time'])
                chunk.sort_values('time', inplace=True)
                chunk.set_index('time', inplace=True)
            yield chunk
    except Exception as e:
        logging.error(f"Failed to fetch historical data: {e}")
        yield pd.DataFrame()
