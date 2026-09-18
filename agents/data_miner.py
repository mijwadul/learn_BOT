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

    def fetch_economic_calendar(self):
        try:
            r = requests.get(Config.MACRO_JSON_URL)
            data = r.json()
            # Filter USD and High impact
            events = [e for e in data if e['country'] == 'USD' and e['impact'] == 'High']
            if not events:
                return pd.DataFrame()
            
            df_events = pd.DataFrame(events)
            # JSON format usually provides iso format or similar for date
            df_events['date'] = pd.to_datetime(df_events['date'], utc=True)
            return df_events[['date', 'title']]
        except Exception as e:
            logging.error(f"Error fetching economic calendar: {e}")
            return pd.DataFrame()

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
        logging.info(f"Starting Historical Backfill for {total_candles} candles...")
        df = self.fetch_and_merge_data(n_candles=total_candles)
        if df is not None:
            logging.info(f"Saving {len(df)} rows to database...")
            # Gunakan pandas to_sql (Replace for now, can be 'append' for incremental)
            df.to_sql('market_data_merged', con=sync_engine, if_exists='replace', index=True)
            logging.info("Backfill complete.")
            return len(df)
        return 0
