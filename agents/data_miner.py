import logging
import requests
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from utils.mt5_utils import get_rates
from utils.indicators import calculate_bbma
from config import Config
from database import sync_engine

logging.basicConfig(level=logging.INFO)

class DataMinerAgent:
    """
    Agent 1: Data Miner (Database & Feature Engineer)
    Menarik data dari MT5, Anti-Leakage MTF Merging, Topografi BBMA, Macro Intelligence.
    """
    
    def __init__(self, symbol=Config.SYMBOL):
        self.symbol = symbol
        self._calendar_cache = pd.DataFrame(columns=['date', 'title'])
        self._last_calendar_fetch = None

    def fetch_economic_calendar(self):
        now = datetime.now(timezone.utc)
        # 1. Gunakan cache jika baru saja diambil dalam 15 menit terakhir (mencegah spam request saat UI rerun)
        if self._last_calendar_fetch is not None and (now - self._last_calendar_fetch).total_seconds() < 900:
            if not self._calendar_cache.empty:
                return self._calendar_cache

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            r = requests.get(Config.MACRO_JSON_URL, headers=headers, timeout=5)
            if r.status_code != 200:
                logging.warning(f"Economic calendar HTTP status {r.status_code}. Menggunakan cache kalender.")
                return self._calendar_cache

            text_content = r.text.strip()
            if not text_content or not text_content.startswith(("[", "{")):
                logging.warning("Economic calendar response bukan format JSON yang valid. Menggunakan cache.")
                return self._calendar_cache

            data = r.json()
            if not isinstance(data, list):
                return self._calendar_cache

            # Filter USD and High impact
            events = [e for e in data if isinstance(e, dict) and e.get('country') == 'USD' and e.get('impact') == 'High']
            if not events:
                self._calendar_cache = pd.DataFrame(columns=['date', 'title'])
            else:
                df_events = pd.DataFrame(events)
                df_events['date'] = pd.to_datetime(df_events['date'], utc=True)
                self._calendar_cache = df_events[['date', 'title']]

            self._last_calendar_fetch = now
            return self._calendar_cache
        except Exception as e:
            logging.warning(f"Gagal mengambil economic calendar ({e}). Menggunakan cache data kalender.")
            return self._calendar_cache

    def merge_macro_data(self, df):
        events_df = self.fetch_economic_calendar()
        df['minutes_to_high_impact_news'] = 9999.0
        
        if events_df.empty:
            return df
            
        # Convert df index (which is MT5 time, roughly UTC+2/3) to UTC for diff
        # Simplification: we'll treat MT5 time as UTC for this diff calculation just to demonstrate
        df_times = df.index.tz_localize('UTC')
        
        for idx, row in events_df.iterrows():
            event_time = row['date']
            # difference in minutes
            diffs = (event_time - df_times).total_seconds() / 60.0
            
            # only future events (diff >= 0)
            valid_mask = diffs >= 0
            if valid_mask.any():
                # assign minimum time to news
                df.loc[valid_mask, 'minutes_to_high_impact_news'] = np.minimum(
                    df.loc[valid_mask, 'minutes_to_high_impact_news'], 
                    diffs[valid_mask]
                )
        return df

    def fetch_and_merge_data(self, n_candles=2000):
        logging.info(f"Fetching data for {self.symbol}...")
        
        df_m1 = get_rates(self.symbol, mt5.TIMEFRAME_M1, n_candles)
        df_m5 = get_rates(self.symbol, mt5.TIMEFRAME_M5, int(n_candles/5) + 50)
        df_m15 = get_rates(self.symbol, mt5.TIMEFRAME_M15, int(n_candles/15) + 50)
        
        if df_m1 is None or df_m5 is None or df_m15 is None:
            logging.error("Failed to fetch data.")
            return None

        # Set index
        df_m1.set_index('time', inplace=True)
        df_m5.set_index('time', inplace=True)
        df_m15.set_index('time', inplace=True)

        # Feature engineering BBMA per timeframe
        df_m1 = calculate_bbma(df_m1)
        df_m5 = calculate_bbma(df_m5)
        df_m15 = calculate_bbma(df_m15)
        
        # Anti-Leakage MTF Merging: shift(1) for higher timeframes before merging to avoid lookahead bias
        df_m5_shifted = df_m5.shift(1).add_suffix('_m5')
        df_m15_shifted = df_m15.shift(1).add_suffix('_m15')
        
        # Merge to M1
        df_merged = df_m1.join(df_m5_shifted, how='left')
        df_merged = df_merged.join(df_m15_shifted, how='left')
        
        # Forward fill AFTER joining
        df_merged.ffill(inplace=True)
        df_merged.dropna(inplace=True)
        
        # Tambahkan data makro
        df_merged = self.merge_macro_data(df_merged)
        
        # Konversi semua tipe data unsigned int (uint8, uint16, uint32, uint64) ke int64
        for col in df_merged.columns:
            if str(df_merged[col].dtype).startswith('uint'):
                df_merged[col] = df_merged[col].astype('int64')
        
        logging.info(f"Data merged successfully. Shape: {df_merged.shape}")
        return df_merged

    def backfill_data(self, total_candles=20000):
        logging.info(f"Starting Historical Backfill / Incremental Download...")
        try:
            # Check schema first
            query = "SELECT * FROM market_data_merged LIMIT 1"
            sample_df = pd.read_sql(query, con=sync_engine)
            if 'upper_wick' not in sample_df.columns:
                raise Exception("Outdated schema: missing upper_wick (candlestick pattern features)")
                
            # Check last date in DB
            query_max = "SELECT MAX(time) as last_time FROM market_data_merged"
            last_date_df = pd.read_sql(query_max, con=sync_engine)
            last_time = pd.to_datetime(last_date_df['last_time'].iloc[0])
        except Exception as e:
            logging.info(f"Existing table missing or outdated schema. Forcing full backfill. Detail: {e}")
            from sqlalchemy import text
            try:
                with sync_engine.begin() as conn:
                    conn.execute(text("DROP TABLE IF EXISTS market_data_merged"))
            except Exception as drop_e:
                pass
            last_time = pd.NaT

        if pd.isna(last_time):
            logging.info(f"No existing data found. Downloading {total_candles} candles.")
            candles_to_fetch = total_candles
            if_exists = 'append'
        else:
            # Make last_time timezone aware if it isn't
            if last_time.tzinfo is None:
                last_time = last_time.tz_localize('UTC')
            now_utc = datetime.now(timezone.utc)
            # Estimate missing M1 candles (diff in minutes)
            missing_minutes = int((now_utc - last_time).total_seconds() / 60)
            
            # Tambahkan buffer
            candles_to_fetch = missing_minutes + 100
            
            if candles_to_fetch < 100:
                logging.info("Database is already up to date.")
                return 0
                
            logging.info(f"Found existing data up to {last_time}. Fetching ~{candles_to_fetch} new candles.")
            if_exists = 'append'

        # Ensure we don't fetch more than total_candles if missing is huge
        candles_to_fetch = min(candles_to_fetch, total_candles)
        
        df = self.fetch_and_merge_data(n_candles=candles_to_fetch)
        
        if df is not None and not df.empty:
            if not pd.isna(last_time):
                # Filter to only insert new rows
                # Assumes df.index is tz-aware UTC
                if df.index.tzinfo is None:
                    df.index = df.index.tz_localize('UTC')
                df = df[df.index > last_time]
                
            if not df.empty:
                total_rows = len(df)
                chunk_size = 50000
                total_batches = (total_rows + chunk_size - 1) // chunk_size
                logging.info(f"Saving {total_rows:,} new rows to database in {total_batches} batches (chunksize={chunk_size:,})...")

                for batch_idx, start_idx in enumerate(range(0, total_rows, chunk_size), 1):
                    end_idx = min(start_idx + chunk_size, total_rows)
                    chunk_df = df.iloc[start_idx:end_idx]
                    
                    chunk_df.to_sql(
                        'market_data_merged',
                        con=sync_engine,
                        if_exists='append',
                        index=True,
                        chunksize=chunk_size,
                        method='multi'
                    )
                    
                    pct = (end_idx / total_rows) * 100
                    logging.info(
                        f"[DB Progress] Batch {batch_idx}/{total_batches} selesai: "
                        f"{end_idx:,}/{total_rows:,} baris ({pct:.1f}%) tersimpan ke database."
                    )

                logging.info("Backfill/Incremental complete.")
                return len(df)
            else:
                logging.info("No new rows to insert after filtering.")
                return 0
        return 0

    def load_from_db(self):
        logging.info("Loading all data from database for training...")
        try:
            df = pd.read_sql("SELECT * FROM market_data_merged ORDER BY time ASC", con=sync_engine, index_col='time')
            # Konversi index kembali ke datetime UTC jika diperlukan (read_sql biasanya mengembalikan string jika SQLite/tidak ter-parse sempurna, namun psycopg2 parsing otomatis)
            df.index = pd.to_datetime(df.index)
            logging.info(f"Loaded {len(df)} rows from database.")
            return df
        except Exception as e:
            logging.error(f"Failed to load data from database: {e}")
            return None

    def load_train_chunks(self, chunk_size=100000, split_ratio=0.80):
        try:
            query_count = "SELECT COUNT(*) FROM market_data_merged"
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            train_limit = int(total_rows * split_ratio)
            
            if train_limit == 0:
                logging.error("Tidak ada data di database untuk dilatih.")
                return 0, None
                
            total_chunks = (train_limit + chunk_size - 1) // chunk_size
            logging.info(f"Mempersiapkan {total_chunks} chunks untuk training (total {train_limit} baris).")
            
            def chunk_generator():
                for offset in range(0, train_limit, chunk_size):
                    limit = min(chunk_size, train_limit - offset)
                    query = f"SELECT * FROM market_data_merged ORDER BY time ASC LIMIT {limit} OFFSET {offset}"
                    df = pd.read_sql(query, con=sync_engine, index_col='time')
                    df.index = pd.to_datetime(df.index)
                    yield df
                    
            return total_chunks, chunk_generator()
        except Exception as e:
            logging.error(f"Gagal memuat train chunks: {e}")
            return 0, None
            
    def load_test_data(self, split_ratio=0.80):
        try:
            query_count = "SELECT COUNT(*) FROM market_data_merged"
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            train_limit = int(total_rows * split_ratio)
            test_limit = total_rows - train_limit
            
            if test_limit == 0:
                return None
                
            query = f"SELECT * FROM market_data_merged ORDER BY time ASC LIMIT {test_limit} OFFSET {train_limit}"
            df = pd.read_sql(query, con=sync_engine, index_col='time')
            df.index = pd.to_datetime(df.index)
            return df
        except Exception as e:
            logging.error(f"Gagal memuat test data: {e}")
            return None
