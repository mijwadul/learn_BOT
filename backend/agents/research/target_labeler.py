import logging
import numpy as np
import pandas as pd
from utils.indicators import calculate_atr, calculate_ema, calculate_lwma

def generate_targets(df: pd.DataFrame, max_runner_rr: float = 5.0) -> pd.DataFrame:
    """
    Generating dynamic ATR-based targets (BBMA LWMA Topography: Buy at LWMA Low, Sell at LWMA High).
    Target_Normal: Scalping RR 1:2
    Target_Runner: Dynamic learned RR (default up to max_runner_rr)
    """
    logging.info("Generating dynamic ATR-based targets (BBMA LWMA Topography)...")
    
    if 'ATR_14' not in df.columns:
        df['ATR_14'] = calculate_atr(df, 14)
        
    if 'EMA_50' not in df.columns:
        df['EMA_50'] = calculate_ema(df['close'], 50)
        
    if 'dist_Close_EMA50' not in df.columns:
        df['dist_Close_EMA50'] = df['close'] - df['EMA_50']
        
    if 'LWMA_5_Low' not in df.columns:
        df['LWMA_5_Low'] = calculate_lwma(df['low'], 5)
    if 'LWMA_10_Low' not in df.columns:
        df['LWMA_10_Low'] = calculate_lwma(df['low'], 10)
    if 'LWMA_5_High' not in df.columns:
        df['LWMA_5_High'] = calculate_lwma(df['high'], 5)
    if 'LWMA_10_High' not in df.columns:
        df['LWMA_10_High'] = calculate_lwma(df['high'], 10)

    closes = df['close'].values
    highs = df['high'].values
    lows = df['low'].values
    atrs = df['ATR_14'].values
    ema_50_vals = df['EMA_50'].values if 'EMA_50' in df.columns else closes
    sma_20_vals = df['SMA_20'].values if 'SMA_20' in df.columns else closes
    bb_upper_vals = df['BB_Upper'].values if 'BB_Upper' in df.columns else (closes + atrs * 2.0)
    bb_lower_vals = df['BB_Lower'].values if 'BB_Lower' in df.columns else (closes - atrs * 2.0)
    
    lwma_low_zone = np.maximum(df['LWMA_5_Low'].values, df['LWMA_10_Low'].values)
    lwma_high_zone = np.minimum(df['LWMA_5_High'].values, df['LWMA_10_High'].values)
    
    n = len(df)
    labels_normal = np.zeros(n)
    labels_runner = np.zeros(n)
    
    opens = df['open'].values if 'open' in df.columns else closes

    for i in range(n):
        if np.isnan(atrs[i]) or np.isnan(lwma_low_zone[i]) or np.isnan(lwma_high_zone[i]):
            continue
            
        # Syarat Re-entry & Zon Zero Loss BBMA Oma Ally (Slide 20, 21, 33, 51-56):
        # 1. Buy Re-entry:
        #    - Low menguji zona LWMA Low
        #    - Slide 33: Body rejection (close tidak jebol ke bawah Mid BB)
        #    - Slide 20: Bukan CSM (close tidak tembus ke atas Top BB)
        #    - Slide 51-56: Trend Bullish ZZL (Mid BB >= EMA 50 dan Close >= EMA 50)
        #    - Konfirmasi Rejection Candle: Candle harus ditutup hijau/bullish (Close >= Open)
        eval_buy = (
            (lows[i] <= lwma_low_zone[i]) and 
            (closes[i] >= sma_20_vals[i]) and 
            (closes[i] <= bb_upper_vals[i]) and 
            (sma_20_vals[i] >= ema_50_vals[i]) and
            (closes[i] >= ema_50_vals[i]) and
            (closes[i] >= opens[i])
        )

        # 2. Sell Re-entry:
        #    - High menguji zona LWMA High
        #    - Slide 33: Body rejection (close tidak jebol ke atas Mid BB)
        #    - Slide 20: Bukan CSM (close tidak tembus ke bawah Low BB)
        #    - Slide 51-56: Trend Bearish ZZL (Mid BB <= EMA 50 dan Close <= EMA 50)
        #    - Konfirmasi Rejection Candle: Candle harus ditutup merah/bearish (Close <= Open)
        eval_sell = (
            (highs[i] >= lwma_high_zone[i]) and 
            (closes[i] <= sma_20_vals[i]) and 
            (closes[i] >= bb_lower_vals[i]) and 
            (sma_20_vals[i] <= ema_50_vals[i]) and
            (closes[i] <= ema_50_vals[i]) and
            (closes[i] <= opens[i])
        )

        if not eval_buy and not eval_sell:
            continue

        # Slide 20 & 21: Titik Entry adalah di level batas zona LWMA Re-entry (MA 5 / MA 10)
        entry_buy = lwma_low_zone[i]
        entry_sell = lwma_high_zone[i]
        
        # Proteksi SL adaptif ATR (minimal 0.5 poin untuk Gold M1)
        sl_dist = max(float(atrs[i]), 0.5)
        
        # Target Normal: Tetap RR murni 1:2 (TP 2x SL, SL 1x SL)
        tp_buy_normal = entry_buy + (sl_dist * 2.0)
        sl_buy_normal = entry_buy - sl_dist
        tp_sell_normal = entry_sell - (sl_dist * 2.0)
        sl_sell_normal = entry_sell + sl_dist
        
        # Target Runner: RR dinamis
        runner_rr = max_runner_rr
        tp_buy_runner = entry_buy + (sl_dist * runner_rr)
        sl_buy_runner = entry_buy - sl_dist
        tp_sell_runner = entry_sell - (sl_dist * runner_rr)
        sl_sell_runner = entry_sell + sl_dist

        # 1. Evaluasi Setup BUY (Triple Barrier Method Murni)
        if eval_buy:
            buy_success_n = False
            horizon_n = min(i + 121, n)
            for j in range(i + 1, horizon_n):
                if lows[j] <= sl_buy_normal:
                    break
                elif highs[j] >= tp_buy_normal:
                    buy_success_n = True
                    break
            if buy_success_n:
                labels_normal[i] = 1

            buy_success_r = False
            horizon_r = min(i + 301, n)
            for j in range(i + 1, horizon_r):
                if lows[j] <= sl_buy_runner:
                    break
                elif highs[j] >= tp_buy_runner:
                    buy_success_r = True
                    break
            if buy_success_r:
                labels_runner[i] = 1

        # 2. Evaluasi Setup SELL (Triple Barrier Method Murni)
        if eval_sell:
            sell_success_n = False
            horizon_n = min(i + 121, n)
            for j in range(i + 1, horizon_n):
                if highs[j] >= sl_sell_normal:
                    break
                elif lows[j] <= tp_sell_normal:
                    sell_success_n = True
                    break
            if sell_success_n:
                labels_normal[i] = 2

            sell_success_r = False
            horizon_r = min(i + 301, n)
            for j in range(i + 1, horizon_r):
                if highs[j] >= sl_sell_runner:
                    break
                elif lows[j] <= tp_sell_runner:
                    sell_success_r = True
                    break
            if sell_success_r:
                labels_runner[i] = 2
                    
    df['Target_Normal'] = labels_normal
    df['Target_Runner'] = labels_runner
    return df
