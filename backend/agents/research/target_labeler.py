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

        # Realistis: Entry pada candle close konfirmasi (bukan retroaktif fill di dasar/ujung shadow)
        entry_buy = closes[i]
        entry_sell = closes[i]
        
        atr_i = float(atrs[i]) if atrs[i] > 0 else 0.001
        min_sl = 0.5 * atr_i
        max_sl = 2.5 * atr_i
        lookback_idx = max(0, i - 9)

        # Dynamic Structural SL untuk BUY (Berdasarkan Support & Setup Invalidation)
        recent_low = float(np.min(lows[lookback_idx:i+1]))
        buy_supports = [recent_low]
        if ema_50_vals[i] > 0 and ema_50_vals[i] < entry_buy:
            buy_supports.append(float(ema_50_vals[i]))
        if sma_20_vals[i] > 0 and sma_20_vals[i] < entry_buy:
            buy_supports.append(float(sma_20_vals[i]))
        support_level = min(buy_supports)
        raw_sl_buy = (entry_buy - support_level) + (0.2 * atr_i)
        sl_dist_buy = max(min_sl, min(max_sl, raw_sl_buy))

        # Dynamic Structural SL untuk SELL (Berdasarkan Resistance & Setup Invalidation)
        recent_high = float(np.max(highs[lookback_idx:i+1]))
        sell_resists = [recent_high]
        if ema_50_vals[i] > entry_sell:
            sell_resists.append(float(ema_50_vals[i]))
        if sma_20_vals[i] > entry_sell:
            sell_resists.append(float(sma_20_vals[i]))
        resist_level = max(sell_resists)
        raw_sl_sell = (resist_level - entry_sell) + (0.2 * atr_i)
        sl_dist_sell = max(min_sl, min(max_sl, raw_sl_sell))
        
        # Target Normal: Tetap RR murni 1:2
        tp_buy_normal = entry_buy + (sl_dist_buy * 2.0)
        sl_buy_normal = entry_buy - sl_dist_buy
        tp_sell_normal = entry_sell - (sl_dist_sell * 2.0)
        sl_sell_normal = entry_sell + sl_dist_sell
        
        # Target Runner: RR dinamis
        runner_rr = max_runner_rr
        tp_buy_runner = entry_buy + (sl_dist_buy * runner_rr)
        sl_buy_runner = entry_buy - sl_dist_buy
        tp_sell_runner = entry_sell - (sl_dist_sell * runner_rr)
        sl_sell_runner = entry_sell + sl_dist_sell

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
