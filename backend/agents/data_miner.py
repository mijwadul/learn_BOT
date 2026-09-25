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
from sqlalchemy import text

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
        self._last_csv_mtime = 0

    def get_live_calendar(self):
        """Ambil data minggu ini dari database lokal, dan auto-sync jika CSV MQL5 berubah."""
        import os
        from database import get_macro_data
        
        # Auto-sync logic: cek apakah EA MQL5 baru saja memperbarui file CSV
        info = mt5.terminal_info()
        if info is not None:
            csv_path = os.path.join(info.data_path, "MQL5", "Files", "economic_calendar.csv")
            if os.path.exists(csv_path):
                current_mtime = os.path.getmtime(csv_path)
                if current_mtime > getattr(self, '_last_csv_mtime', 0):
                    self.sync_mt5_calendar_to_db()
                    self._last_csv_mtime = current_mtime
                    
        now = datetime.now(timezone.utc)
        start_date = (now - pd.Timedelta(days=now.weekday())).strftime('%Y-%m-%d')
        end_date = (now + pd.Timedelta(days=(6 - now.weekday()))).strftime('%Y-%m-%d')
        return get_macro_data(start_date, end_date)

    def sync_mt5_calendar_to_db(self):
        """
        Membaca file economic_calendar.csv yang dihasilkan oleh EA MQL5 (MacroBridge.mq5)
        dan menyimpannya ke database PostgreSQL.
        """
        import os
        from database import save_macro_data
        
        info = mt5.terminal_info()
        if info is None:
            logging.error("MT5 terminal_info is None. Pastikan MT5 berjalan.")
            return pd.DataFrame()
            
        data_path = info.data_path
        csv_path = os.path.join(data_path, "MQL5", "Files", "economic_calendar.csv")
        
        if not os.path.exists(csv_path):
            logging.error(f"File {csv_path} tidak ditemukan. Pastikan MacroBridge.mq5 berjalan di MT5.")
            return pd.DataFrame()
            
        try:
            df = pd.read_csv(csv_path)
            if df.empty:
                return df
                
            # Rename columns to match save_macro_data expectations
            if 'event_name' in df.columns:
                df.rename(columns={'event_name': 'event'}, inplace=True)
                
            df['date'] = pd.to_datetime(df['date'], utc=True)
            
            # Hitung 'change' (Actual - Previous) jika kolom tersedia
            if 'actual' in df.columns and 'previous' in df.columns:
                df['change'] = df['actual'] - df['previous']
            else:
                df['change'] = None
                
            # Save to db
            count = save_macro_data(df)
            logging.info(f"Berhasil mensinkronisasi {count} event dari MT5 ke database.")
            return df
        except Exception as e:
            logging.error(f"Gagal membaca atau memproses CSV dari MT5: {e}")
            return pd.DataFrame()

    def merge_macro_data(self, df):
        # Gunakan rentang tanggal dari df untuk mengambil macro data dari DB
        if df.empty:
            return df
            
        start_date = df.index.min().strftime('%Y-%m-%d')
        end_date = df.index.max().strftime('%Y-%m-%d')
        
        # Panggil get_live_calendar untuk memastikan data minggu ini ada (jika ini live data)
        self.get_live_calendar()
        
        from database import get_macro_data
        events_df = get_macro_data(start_date, end_date)
        
        df = df.copy()
        df['minutes_to_high_impact_news'] = 9999.0
        df['actual_vs_estimate_surprise'] = 0.0
        
        if events_df.empty:
            return df
            
        df_times = df.index
        if df_times.tzinfo is None:
            df_times = df_times.tz_localize('UTC')
        
        for idx, row in events_df.iterrows():
            event_time = row['date']
            diffs = (event_time - df_times).total_seconds() / 60.0
            
            # 1. minutes_to_high_impact_news (only future events diff >= 0)
            valid_mask = diffs >= 0
            if valid_mask.any():
                df.loc[valid_mask, 'minutes_to_high_impact_news'] = np.minimum(
                    df.loc[valid_mask, 'minutes_to_high_impact_news'], 
                    diffs[valid_mask]
                )
                
            # 2. actual_vs_estimate_surprise
            if pd.notna(row.get('actual')) and pd.notna(row.get('estimate')):
                surprise = float(row['actual']) - float(row['estimate'])
                surprise_mask = (diffs <= 0) & (diffs >= -60)
                if surprise_mask.any():
                    df.loc[surprise_mask, 'actual_vs_estimate_surprise'] = surprise
                    
        return df

    def fetch_and_merge_data(self, n_candles=2000, start_pos=0):
        logging.info(f"Fetching data for {self.symbol} (pos {start_pos}, count {n_candles})...")
        
        # Buffer warmup agar MA tidak corrupt di perbatasan chunk
        warmup_m1 = 200
        df_m1 = get_rates(self.symbol, mt5.TIMEFRAME_M1, n_candles + warmup_m1, start_pos=start_pos)
        
        start_pos_m5 = max(0, int(start_pos / 5) - 5)
        n_candles_m5 = int(n_candles / 5) + 100
        df_m5 = get_rates(self.symbol, mt5.TIMEFRAME_M5, n_candles_m5, start_pos=start_pos_m5)
        
        start_pos_m15 = max(0, int(start_pos / 15) - 5)
        n_candles_m15 = int(n_candles / 15) + 100
        df_m15 = get_rates(self.symbol, mt5.TIMEFRAME_M15, n_candles_m15, start_pos=start_pos_m15)
        
        if df_m1 is None or df_m5 is None or df_m15 is None:
            # Ini normal jika kita meminta data yang lebih tua dari kapasitas maksimal broker
            return None

        # Set index
        df_m1.set_index('time', inplace=True)
        df_m5.set_index('time', inplace=True)
        df_m15.set_index('time', inplace=True)

        # Feature engineering BBMA & ADX per timeframe
        from utils.indicators import calculate_atr, calculate_adx
        df_m1 = calculate_bbma(df_m1)
        df_m1['ATR_14'] = calculate_atr(df_m1, 14)
        df_m1['adx'] = calculate_adx(df_m1, 14)
        df_m5 = calculate_bbma(df_m5)
        df_m5['adx'] = calculate_adx(df_m5, 14)
        df_m15 = calculate_bbma(df_m15)
        df_m15['adx'] = calculate_adx(df_m15, 14)
        
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
                
        # Potong (slice) bagian warmup agar kita hanya mereturn data asli yang diminta
        if len(df_merged) > n_candles:
            df_merged = df_merged.iloc[-n_candles:]
        
        logging.info(f"Data merged successfully. Shape: {df_merged.shape}")
        return df_merged

    def _save_market_data(self, df, if_exists='append'):
        """
        Menyimpan DataFrame ke tabel market_data_merged dengan aman.
        Menghitung chunksize secara dinamis agar jumlah bind parameter tidak pernah melebihi batas PostgreSQL (65.535 / 32.767).
        Juga memastikan kolom-kolom baru otomatis di-ALTER jika belum ada.
        """
        if df is None or df.empty:
            return 0

        # Pastikan index bersih dari duplikasi dan timezone-naive
        df = df[~df.index.duplicated(keep='last')].sort_index()
        if hasattr(df.index, 'tzinfo') and df.index.tzinfo is not None:
            df.index = df.index.tz_localize(None)

        # Pastikan kolom-kolom baru ada di database jika tabel sudah terbentuk
        try:
            with sync_engine.connect() as conn:
                sample_cols = pd.read_sql("SELECT * FROM market_data_merged LIMIT 0", con=conn).columns
                missing_cols = set(df.columns) - set(sample_cols)
                if missing_cols:
                    logging.info(f"Terdeteksi {len(missing_cols)} kolom baru yang belum ada di database: {missing_cols}")
                    with sync_engine.begin() as alter_conn:
                        for col in missing_cols:
                            dtype_str = str(df[col].dtype)
                            if 'float' in dtype_str:
                                sql_type = 'FLOAT'
                            elif 'int' in dtype_str:
                                sql_type = 'BIGINT'
                            elif 'bool' in dtype_str:
                                sql_type = 'BOOLEAN'
                            else:
                                sql_type = 'TEXT'
                            alter_conn.execute(text(f'ALTER TABLE market_data_merged ADD COLUMN IF NOT EXISTS "{col}" {sql_type}'))
        except Exception as e:
            # Jika tabel belum ada, to_sql akan membuatnya secara otomatis
            logging.debug(f"Pengecekan schema kolom dilewati: {e}")

        # Hitung chunksize aman untuk method='multi'
        # Batas parameter PostgreSQL adalah 65.535 (int16/uint16).
        # Kita gunakan batas aman 30.000 parameter per query INSERT.
        num_cols = len(df.columns) + 1  # +1 untuk kolom time (index)
        safe_chunksize = max(1, 30000 // max(1, num_cols))

        df.to_sql(
            'market_data_merged',
            con=sync_engine,
            if_exists=if_exists,
            index=True,
            chunksize=safe_chunksize,
            method='multi'
        )

        # Buat index pada kolom time jika belum ada untuk mempercepat MAX(time) dan ORDER BY
        try:
            with sync_engine.begin() as conn:
                conn.execute(text('CREATE INDEX IF NOT EXISTS ix_market_data_merged_time ON market_data_merged ("time")'))
        except Exception:
            pass

        return len(df)

    def sync_latest_data(self):
        """
        Sinkronisasi Cepat (Incremental Sync):
        HANYA mengunduh candle baru sejak record terakhir di database hingga saat ini dari MT5.
        TIDAK AKAN me-rebuild atau men-drop tabel market_data_merged.
        """
        logging.info("[SYNC] Memeriksa data terbaru dari MT5...")
        
        # 1. Cek timestamp terakhir di tabel market_data_merged
        last_time = None
        try:
            with sync_engine.connect() as conn:
                result = conn.execute(text('SELECT MAX("time") FROM market_data_merged'))
                row = result.fetchone()
                if row and row[0] is not None:
                    last_time = pd.to_datetime(row[0])
                    if last_time.tzinfo is not None:
                        last_time = last_time.tz_localize(None)
        except Exception as e:
            logging.warning(f"[SYNC] Tidak dapat membaca MAX(time) dari market_data_merged: {e}")
            last_time = None

        # 2. Cek candle terakhir dari MT5
        rates_latest = None
        try:
            rates_latest = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, 1)
        except Exception as e:
            logging.error(f"[SYNC] Error saat copy_rates_from_pos MT5: {e}")

        if rates_latest is None or len(rates_latest) == 0:
            msg = "Gagal mengambil data dari MT5. Pastikan MT5 terbuka dan terhubung ke broker."
            logging.warning(f"[SYNC] {msg}")
            return 0, msg

        mt5_latest_time = pd.to_datetime(rates_latest[0]['time'], unit='s')
        if mt5_latest_time.tzinfo is not None:
            mt5_latest_time = mt5_latest_time.tz_localize(None)

        # 3. Hitung selisih
        if last_time is not None:
            diff_seconds = (mt5_latest_time - last_time).total_seconds()
            missing_candles = int(diff_seconds // 60)
            logging.info(f"[SYNC] DB Max Time: {last_time} | MT5 Current Time: {mt5_latest_time} | Gap: {missing_candles} candles")

            if missing_candles <= 0:
                msg = f"Database sudah up-to-date (Record: {last_time}). Tidak ada candle baru di MT5."
                logging.info(f"[SYNC] {msg}")
                return 0, msg
                
            # Batasi candle yang ditarik (maksimal 50.000 candle untuk satu kali quick sync)
            candles_to_fetch = min(missing_candles, 50000)
        else:
            # Jika database belum ada data sama sekali, ambil 5.000 candle terakhir
            logging.info("[SYNC] Database belum memiliki data. Mengambil 5.000 candle terakhir.")
            candles_to_fetch = 5000

        # 4. Ambil data dari MT5 mulai dari bar 0 (paling baru)
        logging.info(f"[SYNC] Mengambil {candles_to_fetch} candle terbaru dari MT5...")
        df = self.fetch_and_merge_data(n_candles=candles_to_fetch, start_pos=0)

        if df is None or df.empty:
            msg = "Gagal memproses candle dari MT5."
            logging.warning(f"[SYNC] {msg}")
            return 0, msg

        # 5. Filter ketat hanya data yang lebih baru dari last_time
        if df.index.tzinfo is not None:
            df.index = df.index.tz_localize(None)

        if last_time is not None:
            df_new = df[df.index > last_time]
        else:
            df_new = df

        if df_new.empty:
            msg = "Tidak ada candle baru yang valid untuk disimpan."
            logging.info(f"[SYNC] {msg}")
            return 0, msg

        # 6. Simpan (APPEND) ke PostgreSQL tanpa drop menggunakan batch aman
        try:
            inserted = self._save_market_data(df_new, if_exists='append')
            msg = f"Sukses menyambungkan {inserted:,} candle baru ke database!"
            logging.info(f"[SYNC SUCCESS] {msg}")
            return inserted, msg
        except Exception as e:
            err_msg = f"Gagal menyimpan data baru ke database: {e}"
            logging.error(f"[SYNC ERROR] {err_msg}")
            return 0, err_msg

    def backfill_data(self, total_candles=20000, progress_callback=None, force_rebuild=False):
        logging.info(f"Starting Historical Backfill / Incremental Download (Force={force_rebuild})...")
        sample_df = None
        
        if force_rebuild:
            try:
                with sync_engine.begin() as conn:
                    conn.execute(text("DROP TABLE IF EXISTS market_data_merged"))
                logging.warning("Table market_data_merged dropped for forced rebuild.")
            except Exception as e:
                logging.error(f"Failed to drop table market_data_merged: {e}")
                
        try:
            # Check schema first
            query = "SELECT * FROM market_data_merged LIMIT 1"
            sample_df = pd.read_sql(query, con=sync_engine)
                
            # Check last date in DB
            query_max = "SELECT MAX(time) as last_time FROM market_data_merged"
            last_date_df = pd.read_sql(query_max, con=sync_engine)
            last_time = pd.to_datetime(last_date_df['last_time'].iloc[0])
        except Exception as e:
            logging.info(f"Existing table missing or empty. Detail: {e}")
            last_time = pd.NaT

        if force_rebuild:
            last_time = pd.NaT

        if pd.isna(last_time):
            logging.info(f"No existing data found (or forced rebuild). Downloading {total_candles} candles.")
            candles_to_fetch = total_candles
            if_exists = 'replace' if force_rebuild else 'append'
        else:
            # Check latest candle directly from MT5 if available
            rates_last = None
            try:
                rates_last = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, 1)
            except Exception as e:
                logging.warning(f"Failed to query latest MT5 candle: {e}")
                
            last_time_naive = last_time.tz_localize(None) if (hasattr(last_time, 'tzinfo') and last_time.tzinfo is not None) else last_time

            if rates_last is not None and len(rates_last) > 0:
                latest_mt5_time = pd.to_datetime(rates_last[0]['time'], unit='s')
                missing_seconds = (latest_mt5_time - last_time_naive).total_seconds()
                missing_minutes = int(missing_seconds / 60)
                logging.info(f"Latest MT5 time: {latest_mt5_time}, DB max time: {last_time_naive}. Missing minutes: {missing_minutes}")
            else:
                now_utc = datetime.now(timezone.utc)
                last_time_utc = last_time.tz_localize('UTC') if last_time.tzinfo is None else last_time
                missing_minutes = int((now_utc - last_time_utc).total_seconds() / 60)

            if missing_minutes <= 0:
                logging.info(f"Database is already up to date with MT5. Last record: {last_time}")
                return 0
                
            candles_to_fetch = missing_minutes + 100
            logging.info(f"Found existing data up to {last_time}. Fetching ~{candles_to_fetch} new candles.")
            if_exists = 'append'

        # Ensure we don't fetch more than total_candles if missing is huge
        candles_to_fetch = min(candles_to_fetch, total_candles)
        
        # CHUNKED DOWNLOAD LOGIC
        chunk_size_mt5 = 100000
        total_mt5_batches = (candles_to_fetch + chunk_size_mt5 - 1) // chunk_size_mt5
        logging.info(f"Starting chunked MT5 download for {candles_to_fetch:,} candles in {total_mt5_batches} batches...")
        
        total_inserted = 0
        
        for batch_idx in range(total_mt5_batches):
            # Calculate start_pos to fetch oldest data first
            remaining = candles_to_fetch - (batch_idx * chunk_size_mt5)
            current_chunk_size = min(chunk_size_mt5, remaining)
            start_pos = remaining - current_chunk_size
            
            df = self.fetch_and_merge_data(n_candles=current_chunk_size, start_pos=start_pos)
            
            if df is None or df.empty:
                continue
                
            # Handle new column schema alterations only on the first batch if sample_df exists
            if batch_idx == 0 and sample_df is not None:
                missing_cols = set(df.columns) - set(sample_df.columns)
                if missing_cols:
                    try:
                        print(f"[*] Terdeteksi ada {len(missing_cols)} kolom baru yang belum ada di database: {missing_cols}")
                        with sync_engine.begin() as conn:
                            for col in missing_cols:
                                dtype_str = str(df[col].dtype)
                                if 'float' in dtype_str:
                                    sql_type = 'FLOAT'
                                elif 'int' in dtype_str:
                                    sql_type = 'BIGINT'
                                elif 'bool' in dtype_str:
                                    sql_type = 'BOOLEAN'
                                else:
                                    sql_type = 'TEXT'
                                print(f"[*] Menambahkan kolom baru: ALTER TABLE market_data_merged ADD COLUMN \"{col}\" {sql_type}")
                                conn.execute(text(f'ALTER TABLE market_data_merged ADD COLUMN "{col}" {sql_type}'))
                        print("[*] Semua kolom baru berhasil ditambahkan ke database!")
                    except Exception as e:
                        logging.error(f"Failed to add missing columns to database: {e}")

            # Filter incremental data
            if not pd.isna(last_time):
                last_time_cmp = last_time.tz_localize(None) if (hasattr(last_time, 'tzinfo') and last_time.tzinfo is not None) else last_time
                df_index_cmp = df.index.tz_localize(None) if (hasattr(df.index, 'tzinfo') and df.index.tzinfo is not None) else df.index
                df = df[df_index_cmp > last_time_cmp]
                if hasattr(df.index, 'tzinfo') and df.index.tzinfo is not None:
                    df.index = df.index.tz_localize(None)
                
            if not df.empty:
                current_if_exists = 'replace' if (force_rebuild and batch_idx == 0) else 'append'
                rows_in_chunk = self._save_market_data(df, if_exists=current_if_exists)
                total_inserted += rows_in_chunk
                pct = ((batch_idx + 1) / total_mt5_batches) * 100
                logging.info(f"[DB Progress] MT5 Batch {batch_idx+1}/{total_mt5_batches} selesai: {rows_in_chunk:,} baris ({pct:.1f}%) tersimpan ke database.")
                
                if progress_callback:
                    progress_callback(batch_idx + 1, total_mt5_batches, batch_idx + 1, total_mt5_batches)
                    
        logging.info(f"Backfill/Incremental complete. Total inserted: {total_inserted:,}")
        return total_inserted

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

    def load_train_chunks(self, chunk_size=100000, split_ratio=0.80, mode="normal"):
        try:
            query_count = "SELECT COUNT(*) FROM market_data_merged"
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            train_limit = int(total_rows * split_ratio)
            
            if train_limit == 0:
                logging.error("Tidak ada data di database untuk dilatih.")
                return 0, None
                
            total_chunks = (train_limit + chunk_size - 1) // chunk_size
            logging.info(f"Mempersiapkan {total_chunks} chunks untuk training [{mode.upper()}] (total {train_limit} baris).")
            
            def chunk_generator():
                for offset in range(0, train_limit, chunk_size):
                    limit = min(chunk_size, train_limit - offset)
                    query = f"SELECT * FROM market_data_merged ORDER BY time ASC LIMIT {limit} OFFSET {offset}"
                    df = pd.read_sql(query, con=sync_engine, index_col='time')
                    df.index = pd.to_datetime(df.index)
                    yield df
                    
                hn_df = self.load_hard_negatives_and_rlhf(mode=mode)
                if not hn_df.empty:
                    logging.info(f"Menginjeksi {len(hn_df)} baris Hard Negatives & OOS RLHF ({mode.upper()}) sebagai chunk tambahan!")
                    yield hn_df

                live_df = self.load_live_decision_chunk(mode=mode)
                if not live_df.empty:
                    logging.info(f"Menginjeksi {len(live_df)} baris Live Closed Decisions ({mode.upper()}) sebagai chunk feedback!")
                    yield live_df
                    
            return total_chunks + 2, chunk_generator()
        except Exception as e:
            logging.error(f"Gagal memuat train chunks: {e}")
            return 0, None

    def load_live_decision_chunk(self, mode="normal"):
        """Ambil closed live decisions (WIN & LOSS) yang sudah memiliki feature vector lengkap."""
        from database import get_live_decision_samples_for_training
        try:
            df = get_live_decision_samples_for_training(mode=mode)
            if not df.empty:
                logging.info(f"Mengambil {len(df)} live decision closed trades ({mode.upper()}) untuk diinjeksi ke retraining!")
            return df
        except Exception as e:
            logging.error(f"Gagal memuat live decision samples: {e}")
            return pd.DataFrame()
            
    def load_test_chunks(self, chunk_size=100000, split_ratio=0.80):
        try:
            query_count = "SELECT COUNT(*) FROM market_data_merged"
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            train_limit = int(total_rows * split_ratio)
            test_limit = total_rows - train_limit
            
            if test_limit == 0:
                logging.error("Tidak ada data OOS/Test di database.")
                return 0, None
                
            total_chunks = (test_limit + chunk_size - 1) // chunk_size
            logging.info(f"Mempersiapkan {total_chunks} chunks untuk testing/validasi OOS (total {test_limit} baris).")
            
            def chunk_generator():
                for offset in range(0, test_limit, chunk_size):
                    limit = min(chunk_size, test_limit - offset)
                    db_offset = train_limit + offset
                    query = f"SELECT * FROM market_data_merged ORDER BY time ASC LIMIT {limit} OFFSET {db_offset}"
                    df = pd.read_sql(query, con=sync_engine, index_col='time')
                    df.index = pd.to_datetime(df.index)
                    yield df
                    
            return total_chunks, chunk_generator()
        except Exception as e:
            logging.error(f"Gagal memuat test chunks: {e}")
            return 0, None

    def load_hard_negatives_and_rlhf(self, mode="normal"):
        """Ambil data spesifik (termasuk dari OOS) yang memiliki status Hard Negative atau direview oleh RLHF
        spesifik untuk mode yang sedang dilatih (Normal atau Runner).
        Setup yang di-Ignore oleh trader TIDAK diinjeksi — bobotnya tetap netral di training data base."""
        from database import get_hard_negative_ids, get_approved_setup_ids, get_rejected_setup_ids, get_ignored_setup_ids
        try:
            mode_str = mode.lower() if mode else "normal"
            hn_ids  = list(get_hard_negative_ids(mode=mode_str))
            app_ids = list(get_approved_setup_ids(mode=mode_str))
            rej_ids = list(get_rejected_setup_ids(mode=mode_str))
            ign_ids = set(get_ignored_setup_ids(mode=mode_str))  # Diabaikan trader — tidak diinjeksi ke RLHF chunk
            # Batasi Hard Negatives maksimal 500 sampel terbaru agar tidak membanjiri memori & dataset
            MAX_HN = 500
            if len(hn_ids) > MAX_HN:
                hn_ids = hn_ids[-MAX_HN:]

            # Hanya inject HN + Approved + Rejected untuk mode ini, BUKAN Ignored
            inject_ids = list(set(hn_ids + app_ids + rej_ids) - ign_ids)

            if not inject_ids:
                return pd.DataFrame()

            id_list_str = "','".join(inject_ids)
            query = f"SELECT * FROM market_data_merged WHERE time IN ('{id_list_str}') ORDER BY time ASC"
            df = pd.read_sql(query, con=sync_engine, index_col='time')
            if not df.empty:
                df.index = pd.to_datetime(df.index)
            logging.info(f"[RLHF Inject ({mode_str.upper()})] {len(df)} baris (HN={len(hn_ids)}, Approve={len(app_ids)}, Reject={len(rej_ids)}, Ignored={len(ign_ids)} dikecualikan)")
            return df
        except Exception as e:
            logging.error(f"Gagal memuat Hard Negatives & RLHF ({mode}): {e}")
            return pd.DataFrame()

    def load_recent_micro_chunk(self, n_candles=3000):
        """Memuat n_candles candle paling baru dari database untuk Online Learning (Micro-Retrain)."""
        try:
            query = f"SELECT * FROM (SELECT * FROM market_data_merged ORDER BY time DESC LIMIT {n_candles}) sub ORDER BY time ASC"
            df = pd.read_sql(query, con=sync_engine, index_col='time')
            if not df.empty:
                df.index = pd.to_datetime(df.index)
            return df
        except Exception as e:
            logging.error(f"Gagal memuat recent micro chunk: {e}")
            return pd.DataFrame()

