import logging
import numpy as np
import pandas as pd
from utils.indicators import calculate_atr, calculate_ema, calculate_lwma

def generate_targets(df: pd.DataFrame, max_runner_rr: float = 5.0, symbol: str = None) -> pd.DataFrame:
    """
    Generating Dynamic BBMA Lifecycle Targets (Event-Driven Invalidation & Dynamic S/R).
    
    Penyempurnaan Institusional (Adaptive Multi-Pair & Extended Trend Horizon):
    1. Rantai 1 (Runner Horizon Extended): Horizon Runner diperpanjang hingga 240 candle (20 jam di M5)
       untuk menangkap ekspansi tren besar 1:5.0 RR tanpa membebani CPU (menggunakan early-exit execution).
    2. Rantai 2 (Pair-Aware Invalidation): Dynamic buffer disesuaikan dengan profil volatilitas masing-masing pair:
       - XAUUSD / BTCUSD: 0.25 ATR buffer (toleransi liquidity sweep & false-wick dalam).
       - USOIL: 0.20 ATR buffer.
       - GBPUSD / Forex: 0.15 ATR buffer.
    3. Konfirmasi Struktural: Memerlukan 2 candle berturut-turut (consecutive closes) di luar batas
       untuk mengonfirmasi Structure Break sejati, sehingga 1 candle retest wajar tidak langsung membunuh setup.
    """
    logging.info("Generating Dynamic BBMA Lifecycle Targets (Adaptive Pair Invalidation & 240-Candle Runner)...")
    
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
    
    # Deteksi Profil Simbol untuk Toleransi Invalidasi Adaptif
    sym_name = str(symbol or getattr(df, 'attrs', {}).get('symbol') or (df['symbol'].iloc[0] if 'symbol' in df.columns and len(df) > 0 else 'XAUUSD')).upper()
    if 'BTC' in sym_name or 'XAU' in sym_name or 'GOLD' in sym_name:
        pair_struct_buffer_ratio = 0.25 # Emas/Kripto: toleransi wick & liquidity sweep lebih longgar
    elif 'OIL' in sym_name or 'USO' in sym_name:
        pair_struct_buffer_ratio = 0.20 # Minyak: toleransi sedang
    else:
        pair_struct_buffer_ratio = 0.15 # Forex (GBPUSD, dll): struktur lebih disiplin

    n = len(df)
    labels_normal = np.zeros(n)
    labels_runner = np.zeros(n)

    HORIZON_NORMAL_MAX = 90   # 90 candle M5 (7.5 jam) sudah cukup untuk target 1.5R
    HORIZON_RUNNER_MAX = 240  # 240 candle M5 (20 jam) untuk menangkap ekspansi tren swing 5.0R

    for i in range(n):
        atr_i = float(atrs[i]) if (not np.isnan(atrs[i]) and atrs[i] > 0) else 0.001
        if np.isnan(lwma_low_zone[i]) or np.isnan(lwma_high_zone[i]):
            continue
            
        buffer_zone = 0.35 * atr_i
        eval_buy = (lows[i] <= lwma_low_zone[i] + buffer_zone)
        eval_sell = (highs[i] >= lwma_high_zone[i] - buffer_zone)

        if not eval_buy and not eval_sell:
            continue

        entry_price = closes[i]
        lookback_idx = max(0, i - 8)
        struct_tol = pair_struct_buffer_ratio * atr_i

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
            
            tp_normal_target = entry_price + (1.5 * sl_dist_buy)
            tp_runner_target = entry_price + (max_runner_rr * sl_dist_buy)

            hit_tp_normal = False
            hit_tp_runner = False
            is_trap_or_invalidated = False
            secured_be = False
            consecutive_breaks = 0

            horizon_buy = min(i + HORIZON_RUNNER_MAX, n)
            normal_cutoff = min(i + HORIZON_NORMAL_MAX, n)

            for j in range(i + 1, horizon_buy):
                c_close = closes[j]
                c_low = lows[j]
                c_high = highs[j]
                mid_bb = sma_20_vals[j]
                ema_50 = ema_50_vals[j]
                low_bb = bb_lower_vals[j]
                opp_ma = lwma_high_zone[j]

                # A. Deteksi Invalidation Mutlak
                # 1. Hard SL tersentuh (Invalidasi Mutlak)
                if c_low <= hard_sl_buy:
                    is_trap_or_invalidated = True
                    break
                
                # 2. Opposite CSM Sell: Candle Momentum Bearish keluar Lower BB (Invalidasi Mutlak)
                if c_close < low_bb:
                    if not secured_be:
                        is_trap_or_invalidated = True
                    break

                # 3. Structure Broken Dinamis dengan Konfirmasi 2-Candle & Pair Buffer
                struct_baseline = min(mid_bb, ema_50) if ema_50 > 0 else mid_bb
                if c_close < (struct_baseline - struct_tol):
                    consecutive_breaks += 1
                    if consecutive_breaks >= 2:
                        if not secured_be:
                            is_trap_or_invalidated = True
                        break
                else:
                    consecutive_breaks = 0 # Retest berhasil bertahan (Liquidity sweep dipertahankan)

                # B. Deteksi Keberhasilan Target Dinamis
                # Normal TP (1.5R) hanya dihitung dalam horizon normal
                if not hit_tp_normal and j <= normal_cutoff:
                    if (c_high >= opp_ma and (c_high - entry_price) >= (1.0 * sl_dist_buy)) or (c_high >= tp_normal_target):
                        hit_tp_normal = True
                        secured_be = True

                # Runner TP (5.0R) bisa tercapai hingga horizon penuh (240 candle)
                if c_high >= tp_runner_target:
                    hit_tp_runner = True
                    break # Early-exit: Target maksimal sudah tercapai, hemat CPU!

                # Proteksi Trailing Breakeven setelah mengunci profit
                if secured_be and c_low <= entry_price:
                    break # Early-exit: Posisi ditutup impas, simulasi selesai!

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
            
            tp_normal_target = entry_price - (1.5 * sl_dist_sell)
            tp_runner_target = entry_price - (max_runner_rr * sl_dist_sell)

            hit_tp_normal = False
            hit_tp_runner = False
            is_trap_or_invalidated = False
            secured_be = False
            consecutive_breaks = 0

            horizon_sell = min(i + HORIZON_RUNNER_MAX, n)
            normal_cutoff = min(i + HORIZON_NORMAL_MAX, n)

            for j in range(i + 1, horizon_sell):
                c_close = closes[j]
                c_low = lows[j]
                c_high = highs[j]
                mid_bb = sma_20_vals[j]
                ema_50 = ema_50_vals[j]
                top_bb = bb_upper_vals[j]
                opp_ma = lwma_low_zone[j]

                # A. Deteksi Invalidation Mutlak
                # 1. Hard SL tersentuh (Invalidasi Mutlak)
                if c_high >= hard_sl_sell:
                    is_trap_or_invalidated = True
                    break
                
                # 2. Opposite CSM Buy: Candle Momentum Bullish keluar Top BB (Invalidasi Mutlak)
                if c_close > top_bb:
                    if not secured_be:
                        is_trap_or_invalidated = True
                    break

                # 3. Structure Broken Dinamis dengan Konfirmasi 2-Candle & Pair Buffer
                struct_baseline = max(mid_bb, ema_50) if ema_50 > 0 else mid_bb
                if c_close > (struct_baseline + struct_tol):
                    consecutive_breaks += 1
                    if consecutive_breaks >= 2:
                        if not secured_be:
                            is_trap_or_invalidated = True
                        break
                else:
                    consecutive_breaks = 0

                # B. Deteksi Keberhasilan Target Dinamis
                if not hit_tp_normal and j <= normal_cutoff:
                    if (c_low <= opp_ma and (entry_price - c_low) >= (1.0 * sl_dist_sell)) or (c_low <= tp_normal_target):
                        hit_tp_normal = True
                        secured_be = True

                # Runner TP (5.0R) bisa tercapai hingga horizon penuh (240 candle)
                if c_low <= tp_runner_target:
                    hit_tp_runner = True
                    break # Early-exit

                # Proteksi Trailing Breakeven setelah mengunci profit
                if secured_be and c_high >= entry_price:
                    break # Early-exit

            if hit_tp_normal and not is_trap_or_invalidated:
                labels_normal[i] = 1
            if (hit_tp_runner or (hit_tp_normal and secured_be)) and not is_trap_or_invalidated:
                labels_runner[i] = 1

    df['Target_Normal'] = labels_normal
    df['Target_Runner'] = labels_runner
    return df
