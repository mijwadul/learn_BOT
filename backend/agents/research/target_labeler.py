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
    
    lwma_low_zone = np.maximum(df['LWMA_5_Low'].values, df['LWMA_10_Low'].values)
    lwma_high_zone = np.minimum(df['LWMA_5_High'].values, df['LWMA_10_High'].values)
    
    n = len(df)
    labels_normal = np.zeros(n)
    labels_runner = np.zeros(n)
    
    for i in range(n):
        if np.isnan(atrs[i]) or np.isnan(lwma_low_zone[i]) or np.isnan(lwma_high_zone[i]):
            continue
            
        is_lwma_low = lows[i] <= lwma_low_zone[i]
        is_lwma_high = highs[i] >= lwma_high_zone[i]
        
        if not is_lwma_low and not is_lwma_high:
            continue

        if is_lwma_low and is_lwma_high:
            if closes[i] >= ema_50_vals[i]:
                eval_buy = True
                eval_sell = False
            else:
                eval_buy = False
                eval_sell = True
        else:
            eval_buy = is_lwma_low
            eval_sell = is_lwma_high

        entry_price = closes[i]
        sl_dist = atrs[i]
        
        # Target Normal: RR minimal 1:2
        tp_buy_normal = entry_price + (sl_dist * 2.0)
        sl_buy_normal = entry_price - sl_dist
        tp_sell_normal = entry_price - (sl_dist * 2.0)
        sl_sell_normal = entry_price + sl_dist
        
        # Target Runner: RR dinamis
        runner_rr = max_runner_rr
        tp_buy_runner = entry_price + (sl_dist * runner_rr)
        sl_buy_runner = entry_price - sl_dist
        tp_sell_runner = entry_price - (sl_dist * runner_rr)
        sl_sell_runner = entry_price + sl_dist

        # 1. Evaluasi Setup BUY (Triple Barrier Method)
        if eval_buy:
            buy_success_n = False
            hit_sl_n = False
            horizon_n = min(i + 101, n)
            for j in range(i + 1, horizon_n):
                if lows[j] <= sl_buy_normal:
                    hit_sl_n = True
                    break
                elif highs[j] >= tp_buy_normal:
                    buy_success_n = True
                    break
            if buy_success_n:
                labels_normal[i] = 1
            elif not hit_sl_n and horizon_n > (i + 1):
                # Triple Barrier Time-Decay: jika waktu habis (100 bar) tanpa SL dan sudah floating profit >= +1.0R
                final_close_n = closes[horizon_n - 1]
                if (final_close_n - entry_price) >= (1.0 * sl_dist):
                    labels_normal[i] = 1

            buy_success_r = False
            hit_sl_r = False
            horizon_r = min(i + 301, n)
            for j in range(i + 1, horizon_r):
                if lows[j] <= sl_buy_runner:
                    hit_sl_r = True
                    break
                elif highs[j] >= tp_buy_runner:
                    buy_success_r = True
                    break
            if buy_success_r:
                labels_runner[i] = 1
            elif not hit_sl_r and horizon_r > (i + 1):
                # Triple Barrier Time-Decay Runner: jika waktu habis (300 bar) tanpa SL dan sudah floating profit >= +2.0R
                final_close_r = closes[horizon_r - 1]
                if (final_close_r - entry_price) >= (2.0 * sl_dist):
                    labels_runner[i] = 1

        # 2. Evaluasi Setup SELL (Triple Barrier Method)
        if eval_sell:
            sell_success_n = False
            hit_sl_sell_n = False
            horizon_n = min(i + 101, n)
            for j in range(i + 1, horizon_n):
                if highs[j] >= sl_sell_normal:
                    hit_sl_sell_n = True
                    break
                elif lows[j] <= tp_sell_normal:
                    sell_success_n = True
                    break
            if sell_success_n:
                labels_normal[i] = 2
            elif not hit_sl_sell_n and horizon_n > (i + 1):
                # Triple Barrier Time-Decay: jika waktu habis (100 bar) tanpa SL dan sudah floating profit >= +1.0R
                final_close_n = closes[horizon_n - 1]
                if (entry_price - final_close_n) >= (1.0 * sl_dist):
                    labels_normal[i] = 2

            sell_success_r = False
            hit_sl_sell_r = False
            horizon_r = min(i + 301, n)
            for j in range(i + 1, horizon_r):
                if highs[j] >= sl_sell_runner:
                    hit_sl_sell_r = True
                    break
                elif lows[j] <= tp_sell_runner:
                    sell_success_r = True
                    break
            if sell_success_r:
                labels_runner[i] = 2
            elif not hit_sl_sell_r and horizon_r > (i + 1):
                # Triple Barrier Time-Decay Runner: jika waktu habis (300 bar) tanpa SL dan sudah floating profit >= +2.0R
                final_close_r = closes[horizon_r - 1]
                if (entry_price - final_close_r) >= (2.0 * sl_dist):
                    labels_runner[i] = 2
                    
    df['Target_Normal'] = labels_normal
    df['Target_Runner'] = labels_runner
    return df
