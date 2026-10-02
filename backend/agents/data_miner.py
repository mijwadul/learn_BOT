import logging
import requests
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from utils.mt5_utils import get_rates, resolve_broker_symbol
from utils.indicators import calculate_bbma
from config import Config
from database import sync_engine, get_market_table_name
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)

class DataMinerAgent:
    """
    Agent 1: Data Miner (Database & Feature Engineer)
    Menarik data dari MT5, Anti-Leakage MTF Merging, Topografi BBMA, Macro Intelligence.
    Mendukung Multi-Pair dengan tabel terisolasi (market_data_{symbol}).
    """
    
    def __init__(self, symbol=Config.SYMBOL):
        self.set_symbol(symbol)
        self._calendar_cache = pd.DataFrame(columns=['date', 'title'])
        self._last_calendar_fetch = None
        self._last_csv_mtime = 0

    def set_symbol(self, symbol):
        if not symbol or str(symbol).upper() == "AUTO":
            self.canonical_symbol = "XAUUSD"
        else:
            self.canonical_symbol = str(symbol).upper()
        self.broker_symbol = resolve_broker_symbol(self.canonical_symbol)
        mt5.symbol_select(self.broker_symbol, True)
        self.symbol = self.broker_symbol
        self.table_name = get_market_table_name(self.canonical_symbol)
        logging.info(f"[DATA MINER] Target pair set: Canonical={self.canonical_symbol} | Broker={self.broker_symbol} | Table={self.table_name}")


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

    def get_pair_timeframe(self) -> str:
        """Membaca timeframe aktif dari model metadata jika tersedia, fallback ke Config."""
        try:
            from agents.research.model_manager import ModelManager
            meta = ModelManager.load_models(self.canonical_symbol)
            if meta and meta.get("timeframe"):
                return meta.get("timeframe")
        except Exception:
            pass
        tf_profile = Config.get_timeframe_profile(self.canonical_symbol)
        return tf_profile.get("entry_tf", "M5")

    def fetch_and_calculate_bbma(self, n_candles=2000, start_pos=0, timeframe=None):
        """
        Menarik data harga dari MT5 dan menghitung indikator BBMA murni:
        - OHLC & Tick Volume
        - Bollinger Bands (20, 2): sma_20, bb_upper, bb_lower
        - EMA 50: ema_50
        - 4 Garis LWMA Terpisah: lwma_5_high, lwma_10_high, lwma_5_low, lwma_10_low
        """
        tf_str = timeframe or self.get_pair_timeframe() or "M15"
        from agents.research.timeframe_finder import get_mt5_timeframe_constant, resample_m1_df
        tf_const = get_mt5_timeframe_constant(tf_str)
        warmup = 100

        logging.info(
            f"Fetching OHLCV + BBMA data for {self.canonical_symbol} [{self.broker_symbol}] "
            f"(Timeframe: {tf_str}, count: {n_candles})..."
        )

        if tf_const is not None:
            # Native MT5 timeframe (M1..M30, H1..H12, D1)
            df = get_rates(self.broker_symbol, tf_const, n_candles + warmup, start_pos=start_pos)
            if df is None or df.empty:
                return None
            df.set_index('time', inplace=True)
        else:
            # Custom Non-Native Timeframe (M7, M35, etc.) via Synthetic M1 Live Aggregator
            import re
            m_min = re.match(r"^M(\d+)$", tf_str.upper())
            mins = int(m_min.group(1)) if m_min else 15
            m1_needed = min((n_candles + warmup) * mins, 80000)
            df_m1 = get_rates(self.broker_symbol, mt5.TIMEFRAME_M1, m1_needed, start_pos=start_pos)
            if df_m1 is None or df_m1.empty:
                return None
            df_m1.set_index('time', inplace=True)
            df = resample_m1_df(df_m1, tf_str)

        df = calculate_bbma(df)

        # Standardize nama kolom ke lowercase
        col_mapping = {
            'SMA_20': 'sma_20',
            'BB_Upper': 'bb_upper',
            'BB_Lower': 'bb_lower',
            'EMA_50': 'ema_50',
            'LWMA_5_High': 'lwma_5_high',
            'LWMA_10_High': 'lwma_10_high',
            'LWMA_5_Low': 'lwma_5_low',
            'LWMA_10_Low': 'lwma_10_low',
        }
        for old_c, new_c in col_mapping.items():
            if old_c in df.columns:
                df[new_c] = df[old_c]

        df['symbol'] = self.canonical_symbol

        # 16 Kolom Murni Database Sesuai Spesifikasi (termasuk spread riil MT5):
        target_cols = [
            'open', 'high', 'low', 'close', 'tick_volume', 'spread',
            'sma_20', 'bb_upper', 'bb_lower', 'ema_50',
            'lwma_5_high', 'lwma_10_high', 'lwma_5_low', 'lwma_10_low',
            'symbol'
        ]
        available_cols = [c for c in target_cols if c in df.columns]
        df = df[available_cols].dropna().copy()

        if len(df) > n_candles:
            df = df.iloc[-n_candles:]

        logging.info(f"OHLCV + BBMA data siap untuk {self.canonical_symbol} ({tf_str}). Shape: {df.shape}")
        return df

    def fetch_and_merge_data(self, n_candles=2000, start_pos=0, timeframe=None):
        """Kompatibilitas mundur: mengarahkan langsung ke fetch_and_calculate_bbma."""
        return self.fetch_and_calculate_bbma(n_candles=n_candles, start_pos=start_pos, timeframe=timeframe)


    def _save_market_data(self, df, if_exists='append'):
        """
        Menyimpan DataFrame ke tabel khusus pair (self.table_name) dengan aman.
        Menghitung chunksize secara dinamis agar jumlah bind parameter tidak pernah melebihi batas PostgreSQL (65.535 / 32.767).
        Juga memastikan kolom-kolom baru otomatis di-ALTER jika belum ada.
        """
        if df is None or df.empty:
            return 0

        # Pastikan index bersih dari duplikasi dan timezone-naive
        df = df[~df.index.duplicated(keep='last')].sort_index().copy()
        if hasattr(df.index, 'tzinfo') and df.index.tzinfo is not None:
            df.index = df.index.tz_localize(None)

        # Konversi tipe data unsigned integer (uint64/uint32) ke signed integer (int64) untuk PostgreSQL psycopg2
        for col in df.columns:
            if 'uint' in str(df[col].dtype):
                df[col] = df[col].astype('int64')

        # Pastikan kolom-kolom baru ada di database jika tabel sudah terbentuk
        try:
            with sync_engine.connect() as conn:
                sample_cols = pd.read_sql(f'SELECT * FROM "{self.table_name}" LIMIT 0', con=conn).columns
                missing_cols = set(df.columns) - set(sample_cols)
                if missing_cols:
                    logging.info(f"Terdeteksi {len(missing_cols)} kolom baru di {self.table_name}: {missing_cols}")
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
                            alter_conn.execute(text(f'ALTER TABLE "{self.table_name}" ADD COLUMN IF NOT EXISTS "{col}" {sql_type}'))
        except Exception as e:
            # Jika tabel belum ada, to_sql akan membuatnya secara otomatis
            logging.debug(f"Pengecekan schema kolom dilewati: {e}")

        # Hitung chunksize aman untuk method='multi'
        num_cols = len(df.columns) + 1  # +1 untuk kolom time (index)
        safe_chunksize = max(1, 30000 // max(1, num_cols))

        df.to_sql(
            self.table_name,
            con=sync_engine,
            if_exists=if_exists,
            index=True,
            chunksize=safe_chunksize,
            method='multi'
        )

        # Buat index pada kolom time jika belum ada untuk mempercepat MAX(time) dan ORDER BY
        try:
            with sync_engine.begin() as conn:
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS "ix_{self.table_name}_time" ON "{self.table_name}" ("time")'))
        except Exception:
            pass

        return len(df)


    def sync_latest_data(self, timeframe="M1"):
        """
        Sinkronisasi Cepat (Incremental Sync):
        Mengunduh candle baru sejak record terakhir di database hingga saat ini dari MT5.
        """
        logging.info(f"[SYNC] Memeriksa data terbaru dari MT5 untuk {self.canonical_symbol} [{self.broker_symbol}] pada {self.table_name}...")
        
        last_time = None
        try:
            with sync_engine.connect() as conn:
                result = conn.execute(text(f'SELECT MAX("time") FROM "{self.table_name}"'))
                row = result.fetchone()
                if row and row[0] is not None:
                    last_time = pd.to_datetime(row[0])
                    if last_time.tzinfo is not None:
                        last_time = last_time.tz_localize(None)
        except Exception as e:
            if self.canonical_symbol == "XAUUSD":
                try:
                    with sync_engine.connect() as conn:
                        result = conn.execute(text('SELECT MAX("time") FROM "market_data_merged"'))
                        row = result.fetchone()
                        if row and row[0] is not None:
                            last_time = pd.to_datetime(row[0])
                            if last_time.tzinfo is not None:
                                last_time = last_time.tz_localize(None)
                except Exception:
                    pass
            logging.warning(f"[SYNC] Tidak dapat membaca MAX(time) dari {self.table_name}: {e}")
            last_time = None

        tf_str = timeframe or "M1"
        TF_MAP = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        tf_const = TF_MAP.get(tf_str.upper(), mt5.TIMEFRAME_M1)
        tf_min_map = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
        tf_minutes = tf_min_map.get(tf_str.upper(), 1)

        rates_latest = None
        try:
            rates_latest = mt5.copy_rates_from_pos(self.broker_symbol, tf_const, 0, 1)
        except Exception as e:
            logging.error(f"[SYNC] Error saat copy_rates_from_pos MT5 ({self.broker_symbol}): {e}")

        if rates_latest is None or len(rates_latest) == 0:
            msg = f"Gagal mengambil data dari MT5 untuk {self.broker_symbol}. Pastikan instrumen tersedia di broker."
            logging.warning(f"[SYNC] {msg}")
            return 0, msg

        mt5_latest_time = pd.to_datetime(rates_latest[0]['time'], unit='s')
        if mt5_latest_time.tzinfo is not None:
            mt5_latest_time = mt5_latest_time.tz_localize(None)

        # 3. Hitung selisih
        if last_time is not None:
            diff_seconds = (mt5_latest_time - last_time).total_seconds()
            missing_candles = int(diff_seconds // (60 * tf_minutes))
            logging.info(f"[SYNC] {self.canonical_symbol} ({tf_str}) DB Max Time: {last_time} | MT5 Current Time: {mt5_latest_time} | Gap: {missing_candles} candles")

            if missing_candles <= 0:
                msg = f"Database {self.canonical_symbol} ({tf_str}) sudah up-to-date (Record: {last_time}). Tidak ada candle baru di MT5."
                logging.info(f"[SYNC] {msg}")
                return 0, msg
                
            # Batasi candle yang ditarik (maksimal 50.000 candle untuk satu kali quick sync)
            candles_to_fetch = min(missing_candles, 50000)
        else:
            # Jika database belum ada data sama sekali, ambil 5.000 candle terakhir
            logging.info(f"[SYNC] Database {self.canonical_symbol} belum memiliki data. Mengambil 5.000 candle terakhir ({tf_str}).")
            candles_to_fetch = 5000

        # 4. Ambil data dari MT5 mulai dari bar 0 (paling baru)
        logging.info(f"[SYNC] Mengambil {candles_to_fetch} candle terbaru dari MT5 ({self.broker_symbol}, {tf_str})...")
        df = self.fetch_and_merge_data(n_candles=candles_to_fetch, start_pos=0, timeframe=tf_str)

        if df is None or df.empty:
            msg = f"Gagal memproses candle dari MT5 ({self.broker_symbol})."
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
            msg = f"Tidak ada candle baru yang valid untuk disimpan ({self.canonical_symbol})."
            logging.info(f"[SYNC] {msg}")
            return 0, msg

        # 6. Simpan (APPEND) ke PostgreSQL tanpa drop menggunakan batch aman
        try:
            inserted = self._save_market_data(df_new, if_exists='append')
            msg = f"Sukses menyambungkan {inserted:,} candle baru ke tabel {self.table_name} ({tf_str})!"
            logging.info(f"[SYNC SUCCESS] {msg}")
            return inserted, msg
        except Exception as e:
            err_msg = f"Gagal menyimpan data baru {self.canonical_symbol} ke database: {e}"
            logging.error(f"[SYNC ERROR] {err_msg}")
            return 0, err_msg

    def backfill_data(self, total_candles=None, progress_callback=None, force_rebuild=False, timeframe="M1"):
        tf_str = timeframe or "M1"
        TF_MAP = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
        }
        tf_const = TF_MAP.get(tf_str.upper(), mt5.TIMEFRAME_M1)
        tf_min_map = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
        tf_minutes = tf_min_map.get(tf_str.upper(), 1)

        logging.info(f"Starting Historical Backfill untuk {self.canonical_symbol} [{self.broker_symbol}] pada {self.table_name} (TF={tf_str}, Force={force_rebuild})...")
        
        if force_rebuild:
            try:
                with sync_engine.begin() as conn:
                    conn.execute(text(f'DROP TABLE IF EXISTS "{self.table_name}"'))
                logging.info(f"Tabel {self.table_name} di-drop untuk full rebuild.")
            except Exception as e:
                logging.error(f"Gagal drop tabel {self.table_name}: {e}")
            last_time = pd.NaT
        else:
            try:
                query_max = f'SELECT MAX(time) as last_time FROM "{self.table_name}"'
                last_date_df = pd.read_sql(query_max, con=sync_engine)
                last_time = pd.to_datetime(last_date_df['last_time'].iloc[0])
            except Exception:
                last_time = pd.NaT

        if pd.isna(last_time):
            chunk_size_mt5 = 50000
            current_pos = 0
            batch_idx = 0
            total_inserted = 0

            while True:
                req_count = chunk_size_mt5
                if total_candles is not None:
                    remaining = total_candles - total_inserted
                    if remaining <= 0:
                        break
                    req_count = min(chunk_size_mt5, remaining)

                df = self.fetch_and_merge_data(n_candles=req_count, start_pos=current_pos, timeframe=tf_str)
                if df is None or df.empty:
                    break

                actual_len = len(df)
                current_if_exists = 'replace' if (force_rebuild and batch_idx == 0) else 'append'
                rows = self._save_market_data(df, if_exists=current_if_exists)
                total_inserted += rows
                current_pos += actual_len
                batch_idx += 1

                logging.info(f"[DB Backfill] Batch {batch_idx} ({rows:,} rows, pos {current_pos:,}) tersimpan ke {self.table_name}. Total: {total_inserted:,}")
                if progress_callback:
                    progress_callback(batch_idx, batch_idx + 1, total_inserted, total_inserted)

                import gc
                del df
                gc.collect()

                if actual_len < req_count:
                    break

            logging.info(f"Backfill selesai untuk {self.canonical_symbol}. Total: {total_inserted:,} candle.")
            return total_inserted
        else:
            rates_last = None
            try:
                rates_last = mt5.copy_rates_from_pos(self.broker_symbol, tf_const, 0, 1)
            except Exception as e:
                logging.warning(f"Gagal cek candle MT5: {e}")

            last_time_naive = last_time.tz_localize(None) if (hasattr(last_time, 'tzinfo') and last_time.tzinfo is not None) else last_time
            if rates_last is not None and len(rates_last) > 0:
                latest_mt5_time = pd.to_datetime(rates_last[0]['time'], unit='s')
                missing_minutes = int((latest_mt5_time - last_time_naive).total_seconds() / (60 * tf_minutes))
            else:
                now_utc = datetime.now(timezone.utc)
                last_time_utc = last_time.tz_localize('UTC') if last_time.tzinfo is None else last_time
                missing_minutes = int((now_utc - last_time_utc).total_seconds() / (60 * tf_minutes))

            if missing_minutes <= 0:
                logging.info(f"Database {self.table_name} sudah sinkron. Record terakhir: {last_time}")
                return 0

            candles_to_fetch = missing_minutes + 100
            df = self.fetch_and_merge_data(n_candles=candles_to_fetch, start_pos=0, timeframe=tf_str)
            if df is not None and not df.empty:
                df_index_cmp = df.index.tz_localize(None) if (hasattr(df.index, 'tzinfo') and df.index.tzinfo is not None) else df.index
                df = df[df_index_cmp > last_time_naive]
                if not df.empty:
                    rows = self._save_market_data(df, if_exists='append')
                    logging.info(f"Incremental sync selesai. Ditambahkan {rows:,} baris ke {self.table_name}.")
                    return rows
            return 0

    def load_from_db(self, symbol=None, chunk_size=50000, max_candles=None):
        if symbol:
            self.set_symbol(symbol)
        try:
            if max_candles:
                query = f'SELECT * FROM (SELECT * FROM "{self.table_name}" ORDER BY time DESC LIMIT {max_candles}) sub ORDER BY time ASC'
            else:
                query = f'SELECT * FROM "{self.table_name}" ORDER BY time ASC'

            chunks = []
            for chunk in pd.read_sql(query, con=sync_engine, chunksize=chunk_size):
                if 'time' in chunk.columns:
                    chunk['time'] = pd.to_datetime(chunk['time'])
                chunks.append(chunk)

            if not chunks:
                return pd.DataFrame()

            df = pd.concat(chunks, ignore_index=True)
            if 'time' in df.columns:
                df.set_index('time', inplace=True)
            elif not isinstance(df.index, pd.DatetimeIndex) and 'time' in df.index.names:
                df.index = pd.to_datetime(df.index)

            del chunks
            import gc
            gc.collect()
            return df
        except Exception as e:
            logging.error(f"Failed to load data from {self.table_name}: {e}")
            return None

    def load_train_chunks(self, chunk_size=100000, split_ratio=0.80, mode="normal", symbol=None):
        if symbol:
            self.set_symbol(symbol)
        try:
            query_count = f'SELECT COUNT(*) FROM "{self.table_name}"'
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            train_limit = int(total_rows * split_ratio)
            
            if train_limit == 0:
                logging.error(f"Tidak ada data di {self.table_name} untuk dilatih.")
                return 0, None
                
            total_chunks = (train_limit + chunk_size - 1) // chunk_size
            logging.info(f"Mempersiapkan {total_chunks} chunks untuk training [{mode.upper()}] ({self.canonical_symbol}) (total {train_limit} baris).")
            
            def chunk_generator():
                for offset in range(0, train_limit, chunk_size):
                    limit = min(chunk_size, train_limit - offset)
                    is_last_chunk = (offset + limit >= train_limit)
                    query = f'SELECT * FROM "{self.table_name}" ORDER BY time ASC LIMIT {limit} OFFSET {offset}'
                    df = pd.read_sql(query, con=sync_engine, index_col='time')
                    df.index = pd.to_datetime(df.index)

                    if is_last_chunk:
                        # Injeksi Live Closed Decisions ke atribut chunk terakhir agar diproses bersamaan (jika ada)

                        # 2. Injeksi Live Closed Decisions ke atribut chunk terakhir agar diproses bersamaan
                        live_df = self.load_live_decision_chunk(mode=mode)
                        if not live_df.empty:
                            logging.info(f"Menyiapkan {len(live_df)} baris Live Closed Decisions ({mode.upper()}) untuk diinjeksi pada chunk terakhir!")
                            df.attrs['live_feedback'] = live_df

                    yield df
                    
            return total_chunks, chunk_generator()
        except Exception as e:
            logging.error(f"Gagal memuat train chunks dari {self.table_name}: {e}")
            return 0, None

    def load_optuna_sample(self, mode="normal", symbol=None, total_sample_candles=60000):
        """
        Multi-Regime Time-Series Sampling untuk Optuna Hyperparameter Optimization:
        Alih-alih hanya mengambil Chunk 1 (awal tahun 2022 saja), fungsi ini mengambil sampel
        blok waktu terdistribusi merata dari rentang 2022 s.d. batas dataset train (80% awal).
        Setiap blok mempertahankan kontinuitas candle agar kalkulasi ATR & masa depan target valid.
        """
        if symbol:
            self.set_symbol(symbol)
        try:
            query_count = f'SELECT COUNT(*) FROM "{self.table_name}"'
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            train_limit = int(total_rows * 0.80)
            
            if train_limit <= 0:
                logging.warning(f"[OPTUNA SAMPLING] Tabel {self.table_name} kosong.")
                return pd.DataFrame()
                
            if train_limit <= total_sample_candles:
                query = f'SELECT * FROM "{self.table_name}" ORDER BY time ASC LIMIT {train_limit}'
                df = pd.read_sql(query, con=sync_engine, index_col='time')
                df.index = pd.to_datetime(df.index)
                return df

            # Ambil 5 blok waktu terpisah secara proporsional melintasi era 2022 - sekarang
            num_blocks = 5
            block_size = max(5000, total_sample_candles // num_blocks)
            offsets = []
            for b in range(num_blocks):
                off = int(b * ((train_limit - block_size) / max(1, num_blocks - 1)))
                offsets.append(off)

            dfs = []
            era_details = []
            for b_idx, off in enumerate(offsets):
                query = f'SELECT * FROM "{self.table_name}" ORDER BY time ASC LIMIT {block_size} OFFSET {off}'
                df_b = pd.read_sql(query, con=sync_engine, index_col='time')
                df_b.index = pd.to_datetime(df_b.index)
                if not df_b.empty:
                    dfs.append(df_b)
                    start_str = df_b.index[0].strftime("%Y-%m-%d")
                    end_str = df_b.index[-1].strftime("%Y-%m-%d")
                    era_details.append(f"Era {b_idx+1}: {start_str} s.d. {end_str} ({len(df_b):,} candle)")

            if not dfs:
                return pd.DataFrame()

            df_merged_sample = pd.concat(dfs)
            df_merged_sample = df_merged_sample[~df_merged_sample.index.duplicated(keep='last')].sort_index()
            logging.info(
                f"[{self.canonical_symbol} OPTUNA SAMPLING] 📦 Berhasil mengekstrak {len(df_merged_sample):,} candle multi-rezim dari {len(dfs)} era pasar:\n" +
                "\n".join([f"   • {d}" for d in era_details])
            )
            return df_merged_sample
        except Exception as e:
            logging.error(f"Gagal memuat optuna multi-regime sample dari {self.table_name}: {e}")
            return pd.DataFrame()

    def load_live_decision_chunk(self, mode="normal", symbol=None):
        """Ambil closed live decisions (WIN & LOSS) yang sudah memiliki feature vector lengkap untuk symbol bersangkutan."""
        from database import get_live_decision_samples_for_training
        try:
            target_sym = (symbol or getattr(self, "canonical_symbol", "XAUUSD") or "XAUUSD").upper()
            df = get_live_decision_samples_for_training(mode=mode, symbol=target_sym)
            if not df.empty:
                logging.info(f"Mengambil {len(df)} live decision closed trades ({mode.upper()} - {target_sym}) untuk diinjeksi ke retraining!")
            return df
        except Exception as e:
            logging.error(f"Gagal memuat live decision samples: {e}")
            return pd.DataFrame()
            
    def load_test_chunks(self, chunk_size=100000, split_ratio=0.80, symbol=None, max_test_samples: int = 50000):
        if symbol:
            self.set_symbol(symbol)
        try:
            query_count = f'SELECT COUNT(*) FROM "{self.table_name}"'
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            train_limit = int(total_rows * split_ratio)
            raw_test_limit = total_rows - train_limit
            
            if raw_test_limit == 0:
                logging.error(f"Tidak ada data OOS/Test di database {self.table_name}.")
                return 0, None
                
            if max_test_samples and raw_test_limit > max_test_samples:
                logging.info(f"⚡ [OOS GUARD] Data OOS ({raw_test_limit} baris) dipangkas ke {max_test_samples} candle terbaru ({self.canonical_symbol}) demi stabilitas CPU/RAM.")
                start_offset = total_rows - max_test_samples
                effective_test_limit = max_test_samples
            else:
                start_offset = train_limit
                effective_test_limit = raw_test_limit

            total_chunks = (effective_test_limit + chunk_size - 1) // chunk_size
            logging.info(f"Mempersiapkan {total_chunks} chunks untuk testing/validasi OOS ({self.canonical_symbol}) (total {effective_test_limit} baris).")
            
            def chunk_generator():
                for offset in range(0, effective_test_limit, chunk_size):
                    limit = min(chunk_size, effective_test_limit - offset)
                    db_offset = start_offset + offset
                    query = f'SELECT * FROM "{self.table_name}" ORDER BY time ASC LIMIT {limit} OFFSET {db_offset}'
                    df = pd.read_sql(query, con=sync_engine, index_col='time')
                    df.index = pd.to_datetime(df.index)
                    yield df
                    
            return total_chunks, chunk_generator()
        except Exception as e:
            logging.error(f"Gagal memuat test chunks dari {self.table_name}: {e}")
            return 0, None

    def load_hard_negatives_and_rlhf(self, mode="normal", symbol=None):
        """Ambil data spesifik (termasuk dari OOS) yang memiliki status Hard Negative atau direview oleh RLHF
        spesifik untuk mode dan pair yang sedang dilatih (Normal atau Runner)."""
        from database import get_hard_negative_ids, get_approved_setup_ids, get_rejected_setup_ids, get_ignored_setup_ids
        try:
            mode_str = mode.lower() if mode else "normal"
            target_sym = (symbol or getattr(self, "canonical_symbol", "XAUUSD") or "XAUUSD").upper()
            hn_ids  = list(get_hard_negative_ids(mode=mode_str, symbol=target_sym))
            app_ids = list(get_approved_setup_ids(mode=mode_str, symbol=target_sym))
            rej_ids = list(get_rejected_setup_ids(mode=mode_str, symbol=target_sym))
            ign_ids = set(get_ignored_setup_ids(mode=mode_str, symbol=target_sym))
            MAX_HN = 500
            if len(hn_ids) > MAX_HN:
                hn_ids = hn_ids[-MAX_HN:]

            inject_ids = list(set(hn_ids + app_ids + rej_ids) - ign_ids)

            # Filter hanya ID yang merupakan format datetime valid untuk kolom time database
            valid_time_ids = []
            for item in inject_ids:
                if not item or not isinstance(item, str):
                    continue
                item_clean = item.strip()
                try:
                    pd.to_datetime(item_clean)
                    valid_time_ids.append(item_clean)
                except Exception:
                    continue

            if not valid_time_ids:
                return pd.DataFrame()

            id_list_str = "','".join(valid_time_ids)
            query = f'SELECT * FROM "{self.table_name}" WHERE time IN (\'{id_list_str}\') ORDER BY time ASC'
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
            query = f'SELECT * FROM (SELECT * FROM "{self.table_name}" ORDER BY time DESC LIMIT {n_candles}) sub ORDER BY time ASC'
            df = pd.read_sql(query, con=sync_engine, index_col='time')
            if not df.empty:
                df.index = pd.to_datetime(df.index)
            return df
        except Exception as e:
            logging.error(f"Gagal memuat recent micro chunk dari {self.table_name}: {e}")
            return pd.DataFrame()


