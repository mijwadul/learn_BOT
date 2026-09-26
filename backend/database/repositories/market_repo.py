import logging
import re
import pandas as pd
from sqlalchemy import text
from ..connection import sync_engine

def get_market_table_name(symbol: str = "XAUUSD") -> str:
    """
    Format nama tabel database per pair: market_data_{symbol_lowercase}.
    Contoh: XAUUSD -> market_data_xauusd, EURUSD -> market_data_eurusd
    """
    if not symbol or str(symbol).upper() == "AUTO":
        clean = "xauusd"
    else:
        clean = re.sub(r'[^a-zA-Z0-9]', '', str(symbol).lower())
    return f"market_data_{clean}"

def get_db_size(symbol: str = "XAUUSD"):
    table_name = get_market_table_name(symbol)
    with sync_engine.connect() as conn:
        try:
            result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
            return result.scalar()
        except Exception:
            # Fallback untuk backward compatibility jika belum termigrasi
            if "xauusd" in table_name:
                try:
                    result = conn.execute(text('SELECT COUNT(*) FROM "market_data_merged"'))
                    return result.scalar()
                except Exception:
                    pass
            return 0

def get_db_date_range(symbol: str = "XAUUSD"):
    table_name = get_market_table_name(symbol)
    with sync_engine.connect() as conn:
        try:
            result = conn.execute(text(f'SELECT MIN(time), MAX(time) FROM "{table_name}"'))
            row = result.fetchone()
            if row:
                return row[0], row[1]
            return None, None
        except Exception:
            if "xauusd" in table_name:
                try:
                    result = conn.execute(text('SELECT MIN(time), MAX(time) FROM "market_data_merged"'))
                    row = result.fetchone()
                    if row:
                        return row[0], row[1]
                except Exception:
                    pass
            return None, None

def fetch_historical_data_chunks(symbol: str = "XAUUSD", chunk_size: int = 10000):
    """
    Mengambil data historis dalam potongan (chunks) dari tabel pair bersangkutan.
    """
    table_name = get_market_table_name(symbol)
    try:
        query = f'SELECT * FROM "{table_name}"'
        for chunk in pd.read_sql(query, con=sync_engine, chunksize=chunk_size):
            if not chunk.empty and 'time' in chunk.columns:
                chunk['time'] = pd.to_datetime(chunk['time'])
                chunk.sort_values('time', inplace=True)
                chunk.set_index('time', inplace=True)
            yield chunk
    except Exception as e:
        if "xauusd" in table_name:
            try:
                query_fb = 'SELECT * FROM "market_data_merged"'
                for chunk in pd.read_sql(query_fb, con=sync_engine, chunksize=chunk_size):
                    if not chunk.empty and 'time' in chunk.columns:
                        chunk['time'] = pd.to_datetime(chunk['time'])
                        chunk.sort_values('time', inplace=True)
                        chunk.set_index('time', inplace=True)
                    yield chunk
                return
            except Exception:
                pass
        logging.error(f"Failed to fetch historical data for {symbol} ({table_name}): {e}")
        yield pd.DataFrame()

