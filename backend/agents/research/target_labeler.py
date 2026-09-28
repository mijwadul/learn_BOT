import logging
import numpy as np
import pandas as pd
from utils.indicators import calculate_atr, calculate_ema, calculate_lwma

def generate_targets(df: pd.DataFrame, max_runner_rr: float = 5.0) -> pd.DataFrame:
    """
    Generating Dynamic BBMA Lifecycle Targets (Event-Driven Invalidation & Dynamic S/R).
    
    Filosofi:
    - Tidak membelenggu kandidat dengan 6 boolean kaku (warna candle, posisi mutlak SMA/EMA),
      sehingga model AI bebas mempelajari sendiri geometri & fitur pembeda setup valid vs jebakan (trap).
    - Label 0 (Trap / Gagal): Terjadi Structure Break dini (Candle Close tembus Mid BB / EMA 50
      atau muncul CSM berlawanan) sebelum target profit tercapai.
    - Label 1 (Profitable): Harga berhasil berekspansi ke MA seberang (TP Wajib) atau membentuk
      CSM searah dengan perolehan R-multiple positif tanpa melanggar struktur.
    """
    logging.info("Generating Dynamic BBMA Lifecycle Targets (Event-Driven Invalidation)...")
    
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

    for i in range(n):
        atr_i = float(atrs[i]) if (not np.isnan(atrs[i]) and atrs[i] > 0) else 0.001
        if np.isnan(lwma_low_zone[i]) or np.isnan(lwma_high_zone[i]):
            continue
            
        # Pemicu Spasial Kandidat: Harga berinteraksi dengan area Re-entry LWMA
        # Memberikan kelonggaran buffer 0.35 ATR tanpa membatasi warna candle atau filter kaku
        buffer_zone = 0.35 * atr_i
        eval_buy = (lows[i] <= lwma_low_zone[i] + buffer_zone)
        eval_sell = (highs[i] >= lwma_high_zone[i] - buffer_zone)

        if not eval_buy and not eval_sell:
            continue

        entry_price = closes[i]
        lookback_idx = max(0, i - 8)

        # -------------------------------------------------------------------------
        # 1. EVALUASI SETUP BUY (BBMA Dynamic Lifecycle Simulation)
        # -------------------------------------------------------------------------
        if eval_buy:
            recent_low = float(np.min(lows[lookback_idx:i+1]))
            buy_supports = [recent_low]
            if ema_50_vals[i] > 0 and ema_50_vals[i] < entry_price:
                buy_supports.append(float(ema_50_vals[i]))
            if sma_20_vals[i] > 0 and sma_20_vals[i] < entry_price:
                buy_supports.append(float(sma_20_vals[i]))
            support_level = min(buy_supports)
            
            raw_sl_buy = (entry_price - support_level) + (0.15 * atr_i)
            sl_dist_buy = max(0.4 * atr_i, min(2.5 * atr_i, raw_sl_buy))
            hard_sl_buy = entry_price - sl_dist_buy
            
            # Target Milestone Dinamis
            tp_normal_target = entry_price + (1.5 * sl_dist_buy)
            tp_runner_target = entry_price + (max_runner_rr * sl_dist_buy)

            hit_tp_normal = False
            hit_tp_runner = False
            is_trap_or_invalidated = False
            secured_be = False

            horizon_buy = min(i + 120, n)
            for j in range(i + 1, horizon_buy):
                c_close = closes[j]
                c_low = lows[j]
                c_high = highs[j]
                mid_bb = sma_20_vals[j]
                ema_50 = ema_50_vals[j]
                low_bb = bb_lower_vals[j]
                opp_ma = lwma_high_zone[j]

                # A. Deteksi Jebakan / Invalidation BBMA (Early Cut-Loss Criteria)
                # 1. Hard SL tersentuh
                if c_low <= hard_sl_buy:
                    is_trap_or_invalidated = True
                    break
                
                # 2. Structure Broken: Candle Close di bawah Mid BB ATAU di bawah EMA 50
                if (c_close < mid_bb - (0.05 * atr_i)) or (ema_50 > 0 and c_close < ema_50 - (0.05 * atr_i)):
                    # Jika belum sempat mengunci profit/BE, ini adalah JEBAKAN (Trap Setup)
                    if not secured_be:
                        is_trap_or_invalidated = True
                    break
                    
                # 3. Opposite CSM Sell: Muncul candle momentum turun keluar Lower BB
                if c_close < low_bb:
                    if not secured_be:
                        is_trap_or_invalidated = True
                    break

                # B. Deteksi Keberhasilan Target Dinamis BBMA
                # 1. TP Wajib: Harga mencapai zona MA High seberang dengan profit >= 1R
                if c_high >= opp_ma and (c_high - entry_price) >= (1.0 * sl_dist_buy):
                    hit_tp_normal = True
                    secured_be = True # Kunci Breakeven

                # 2. Normal Target (1.5R) tercapai
                if c_high >= tp_normal_target:
                    hit_tp_normal = True
                    secured_be = True

                # 3. Runner Target tercapai
                if c_high >= tp_runner_target:
                    hit_tp_runner = True
                    break

                # 4. Jika sudah aman di BE, proteksi floating loss
                if secured_be and c_low <= entry_price:
                    # Trailed out at Breakeven
                    break

            if hit_tp_normal and not is_trap_or_invalidated:
                labels_normal[i] = 1
            if (hit_tp_runner or (hit_tp_normal and secured_be)) and not is_trap_or_invalidated:
                labels_runner[i] = 1

        # -------------------------------------------------------------------------
        # 2. EVALUASI SETUP SELL (BBMA Dynamic Lifecycle Simulation)
        # -------------------------------------------------------------------------
        if eval_sell:
            recent_high = float(np.max(highs[lookback_idx:i+1]))
            sell_resists = [recent_high]
            if ema_50_vals[i] > entry_price:
                sell_resists.append(float(ema_50_vals[i]))
            if sma_20_vals[i] > entry_price:
                sell_resists.append(float(sma_20_vals[i]))
            resist_level = max(sell_resists)
            
            raw_sl_sell = (resist_level - entry_price) + (0.15 * atr_i)
            sl_dist_sell = max(0.4 * atr_i, min(2.5 * atr_i, raw_sl_sell))
            hard_sl_sell = entry_price + sl_dist_sell
            
            # Target Milestone Dinamis
            tp_normal_target = entry_price - (1.5 * sl_dist_sell)
            tp_runner_target = entry_price - (max_runner_rr * sl_dist_sell)

            hit_tp_normal = False
            hit_tp_runner = False
            is_trap_or_invalidated = False
            secured_be = False

            horizon_sell = min(i + 120, n)
            for j in range(i + 1, horizon_sell):
                c_close = closes[j]
                c_low = lows[j]
                c_high = highs[j]
                mid_bb = sma_20_vals[j]
                ema_50 = ema_50_vals[j]
                top_bb = bb_upper_vals[j]
                opp_ma = lwma_low_zone[j]

                # A. Deteksi Jebakan / Invalidation BBMA (Early Cut-Loss Criteria)
                # 1. Hard SL tersentuh
                if c_high >= hard_sl_sell:
                    is_trap_or_invalidated = True
                    break
                
                # 2. Structure Broken: Candle Close di atas Mid BB ATAU di atas EMA 50
                if (c_close > mid_bb + (0.05 * atr_i)) or (ema_50 > 0 and c_close > ema_50 + (0.05 * atr_i)):
                    if not secured_be:
                        is_trap_or_invalidated = True
                    break
                    
                # 3. Opposite CSM Buy: Muncul candle momentum naik keluar Top BB
                if c_close > top_bb:
                    if not secured_be:
                        is_trap_or_invalidated = True
                    break

                # B. Deteksi Keberhasilan Target Dinamis BBMA
                # 1. TP Wajib: Harga mencapai zona MA Low seberang dengan profit >= 1R
                if c_low <= opp_ma and (entry_price - c_low) >= (1.0 * sl_dist_sell):
                    hit_tp_normal = True
                    secured_be = True # Kunci Breakeven

                # 2. Normal Target (1.5R) tercapai
                if c_low <= tp_normal_target:
                    hit_tp_normal = True
                    secured_be = True

                # 3. Runner Target tercapai
                if c_low <= tp_runner_target:
                    hit_tp_runner = True
                    break

                # 4. Jika sudah aman di BE, proteksi floating loss
                if secured_be and c_high >= entry_price:
                    # Trailed out at Breakeven
                    break

            if hit_tp_normal and not is_trap_or_invalidated:
                labels_normal[i] = 1
            if (hit_tp_runner or (hit_tp_normal and secured_be)) and not is_trap_or_invalidated:
                labels_runner[i] = 1

    df['Target_Normal'] = labels_normal
    df['Target_Runner'] = labels_runner
    return df
