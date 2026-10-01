import logging
import numpy as np
import pandas as pd
from utils.indicators import calculate_atr, calculate_ema, calculate_lwma
from .profiles import get_profile


# ---------------------------------------------------------------------------
# TARGET LABELER v2 — Fractal-Aware MFE (Maximum Favorable Excursion)
# ---------------------------------------------------------------------------

HORIZON_BY_FRACTAL = {
    0: 60,
    1: 60,   # Base timeframe only  → 60 candle
    2: 120,  # Setup + Base         → 120 candle
    3: 240   # Trend + Setup + Base → 240 candle
}


def _get_sym_buffer(sym_name: str) -> float:
    """Mengembalikan buffer LWMA zona berdasarkan profil pair."""
    s = sym_name.upper()
    if 'BTC' in s or 'XAU' in s or 'GOLD' in s:
        return 0.25
    elif 'OIL' in s or 'USO' in s:
        return 0.20
    return 0.15


def _find_trigger_score(flags_csa: np.ndarray, flags_csak: np.ndarray, flags_csm: np.ndarray,
                         body_sizes: np.ndarray, atrs: np.ndarray,
                         i: int, lookback: int = 30) -> float:
    """
    Menghitung trigger score komposit untuk bar ke-i:
    CSM > CSAK > CSA dalam hierarki.
    Returns: skor [0, ∞), 0 = tidak ada trigger.
    Dibiarkan kontinu agar AI bisa menemukan ambang batas sendiri.
    """
    decay_k = np.log(2) / 5.0  # half-life 5 candle
    best = 0.0
    for lag in range(1, min(lookback + 1, i + 1)):
        idx = i - lag
        atr_at = float(atrs[idx]) if atrs[idx] > 0 else 1e-5
        body_ratio = float(body_sizes[idx]) / atr_at
        freshness = float(np.exp(-decay_k * lag))
        weight = 3.0 if flags_csm[idx] else (2.0 if flags_csak[idx] else (1.0 if flags_csa[idx] else 0.0))
        score = weight * freshness * body_ratio
        if score > best:
            best = score
    return best


def generate_targets(df: pd.DataFrame, max_runner_rr: float = 5.0, symbol: str = None) -> pd.DataFrame:
    """
    Labeling BBMA Re-entry berbasis MFE Fraktal-Aware (versi 2).

    Menghasilkan kolom:
    - Target_Normal   : 1 jika hit ≥ 1R sebelum invalidasi, 0 sebaliknya
    - Target_Runner   : 1 jika hit ≥ 3R sebelum invalidasi, 0 sebaliknya
    - max_mfe_r       : Nilai MFE tertinggi yang dicapai (kontinu, untuk regresi)
    - trigger_score_i : Skor trigger BBMA saat candle ini (fitur tambahan)
    - fractal_horizon : Horizon simulasi yang digunakan (mencerminkan kekuatan fraktal)
    """
    logging.info("Generating Fractal-Aware MFE Targets (v2 — No Fixed RR, Contextual Sequence)...")

    # --- Pastikan kolom indikator & topografi BB tersedia ---
    regime_cols = ('BB_Upper', 'forbid_buy', 'is_CSA_Buy', 'is_breakout_bull', 'is_running_bull', 'is_bb_squeeze', 'is_bb_expanding')
    if any(c not in df.columns or (c in df.columns and df[c].isna().all()) for c in regime_cols):
        from utils.indicators import calculate_bbma
        df = calculate_bbma(df)

    if 'ATR_14' not in df.columns:
        df['ATR_14'] = calculate_atr(df, 14)
    if 'EMA_50' not in df.columns:
        df['EMA_50'] = calculate_ema(df['close'], 50)
    if 'dist_Close_EMA50' not in df.columns:
        df['dist_Close_EMA50'] = df['close'] - df['EMA_50']
    if 'LWMA_5_Low'   not in df.columns: df['LWMA_5_Low']   = calculate_lwma(df['low'],  5)
    if 'LWMA_10_Low'  not in df.columns: df['LWMA_10_Low']  = calculate_lwma(df['low'],  10)
    if 'LWMA_5_High'  not in df.columns: df['LWMA_5_High']  = calculate_lwma(df['high'], 5)
    if 'LWMA_10_High' not in df.columns: df['LWMA_10_High'] = calculate_lwma(df['high'], 10)

    # --- Array NumPy untuk kecepatan (sanitized numeric) ---
    close_s  = pd.to_numeric(df['close'], errors='coerce').fillna(0.0)
    high_s   = pd.to_numeric(df['high'], errors='coerce').fillna(close_s)
    low_s    = pd.to_numeric(df['low'], errors='coerce').fillna(close_s)
    open_s   = pd.to_numeric(df['open'], errors='coerce').fillna(close_s) if 'open' in df.columns else close_s
    atr_s    = pd.to_numeric(df['ATR_14'], errors='coerce').fillna(0.01) if 'ATR_14' in df.columns else pd.Series(0.01, index=df.index)
    ema50_s  = pd.to_numeric(df['EMA_50'], errors='coerce').fillna(close_s) if 'EMA_50' in df.columns else close_s
    sma20_s  = pd.to_numeric(df['SMA_20'], errors='coerce').fillna(close_s) if 'SMA_20' in df.columns else close_s
    bb_u_s   = pd.to_numeric(df['BB_Upper'], errors='coerce').fillna(close_s + atr_s * 2.0) if 'BB_Upper' in df.columns else (close_s + atr_s * 2.0)
    bb_l_s   = pd.to_numeric(df['BB_Lower'], errors='coerce').fillna(close_s - atr_s * 2.0) if 'BB_Lower' in df.columns else (close_s - atr_s * 2.0)

    lw5l_s   = pd.to_numeric(df['LWMA_5_Low'], errors='coerce').fillna(low_s) if 'LWMA_5_Low' in df.columns else low_s
    lw10l_s  = pd.to_numeric(df['LWMA_10_Low'], errors='coerce').fillna(low_s) if 'LWMA_10_Low' in df.columns else low_s
    lw5h_s   = pd.to_numeric(df['LWMA_5_High'], errors='coerce').fillna(high_s) if 'LWMA_5_High' in df.columns else high_s
    lw10h_s  = pd.to_numeric(df['LWMA_10_High'], errors='coerce').fillna(high_s) if 'LWMA_10_High' in df.columns else high_s

    closes   = close_s.values
    highs    = high_s.values
    lows     = low_s.values
    opens    = open_s.values
    atrs     = atr_s.values
    ema50    = ema50_s.values
    sma20    = sma20_s.values
    bb_upper = bb_u_s.values
    bb_lower = bb_l_s.values

    lwma_low_zone  = np.maximum(lw5l_s.values, lw10l_s.values)
    lwma_high_zone = np.minimum(lw5h_s.values, lw10h_s.values)

    # Topografi & Anti Counter-Trend Arrays
    forbid_buy  = pd.to_numeric(df['forbid_buy'], errors='coerce').fillna(0.0).values if 'forbid_buy' in df.columns else np.zeros(len(df))
    forbid_sell = pd.to_numeric(df['forbid_sell'], errors='coerce').fillna(0.0).values if 'forbid_sell' in df.columns else np.zeros(len(df))
    sq_buy_ok   = pd.to_numeric(df['is_squeeze_buy_allowed'], errors='coerce').fillna(1.0).values if 'is_squeeze_buy_allowed' in df.columns else np.ones(len(df))
    sq_sell_ok  = pd.to_numeric(df['is_squeeze_sell_allowed'], errors='coerce').fillna(1.0).values if 'is_squeeze_sell_allowed' in df.columns else np.ones(len(df))

    # --- Trigger event arrays ---
    is_csa_buy   = pd.to_numeric(df['is_CSA_Buy'], errors='coerce').fillna(0.0).values   if 'is_CSA_Buy'   in df.columns else np.zeros(len(df))
    is_csa_sell  = pd.to_numeric(df['is_CSA_Sell'], errors='coerce').fillna(0.0).values  if 'is_CSA_Sell'  in df.columns else np.zeros(len(df))
    is_csak_buy  = pd.to_numeric(df['is_CSAK_Buy'], errors='coerce').fillna(0.0).values  if 'is_CSAK_Buy'  in df.columns else np.zeros(len(df))
    is_csak_sell = pd.to_numeric(df['is_CSAK_Sell'], errors='coerce').fillna(0.0).values if 'is_CSAK_Sell' in df.columns else np.zeros(len(df))
    is_csm_buy   = pd.to_numeric(df['is_CSM_Buy'], errors='coerce').fillna(0.0).values   if 'is_CSM_Buy'   in df.columns else np.zeros(len(df))
    is_csm_sell  = pd.to_numeric(df['is_CSM_Sell'], errors='coerce').fillna(0.0).values  if 'is_CSM_Sell'  in df.columns else np.zeros(len(df))

    body_sizes = np.abs(closes - opens)

    # --- Profil pair ---
    sym_name = str(
        symbol
        or getattr(df, 'attrs', {}).get('symbol')
        or (df['symbol'].iloc[0] if 'symbol' in df.columns and len(df) > 0 else 'XAUUSD')
    ).upper()
    profile = get_profile(sym_name)
    struct_buf_ratio = profile.zone_buffer_ratio

    # --- Deteksi fractal origin dari kolom hasil calculate_fractal_origin() ---
    frac_buy      = pd.to_numeric(df['fractal_origin_buy'], errors='coerce').fillna(1.0).values  if 'fractal_origin_buy'  in df.columns else np.ones(len(df))
    frac_sell     = pd.to_numeric(df['fractal_origin_sell'], errors='coerce').fillna(1.0).values if 'fractal_origin_sell' in df.columns else np.ones(len(df))
    frac_cap_buy  = pd.to_numeric(df['fractal_capacity_buy'], errors='coerce').fillna(1.0).values  if 'fractal_capacity_buy'  in df.columns else np.ones(len(df))
    frac_cap_sell = pd.to_numeric(df['fractal_capacity_sell'], errors='coerce').fillna(1.0).values if 'fractal_capacity_sell' in df.columns else np.ones(len(df))

    n = len(df)

    # --- Horizons fraktal:
    # fractal_origin score 1 (base only)  → 60 candle
    # fractal_origin score 2 (setup+base) → 120 candle
    # fractal_origin score 3 (all three)  → 240 candle
    # --- Partisi Rezim Pasar untuk Spesialisasi Model Dual AI ---
    is_bb_sq_arr      = pd.to_numeric(df['is_bb_squeeze'], errors='coerce').fillna(0.0).values if 'is_bb_squeeze' in df.columns else np.zeros(n)
    is_bb_exp_arr     = pd.to_numeric(df['is_bb_expanding'], errors='coerce').fillna(0.0).values if 'is_bb_expanding' in df.columns else np.zeros(n)
    is_breakout_b_arr = pd.to_numeric(df['is_breakout_bull'], errors='coerce').fillna(0.0).values if 'is_breakout_bull' in df.columns else np.zeros(n)
    is_breakout_s_arr = pd.to_numeric(df['is_breakout_bear'], errors='coerce').fillna(0.0).values if 'is_breakout_bear' in df.columns else np.zeros(n)
    is_running_b_arr  = pd.to_numeric(df['is_running_bull'], errors='coerce').fillna(0.0).values if 'is_running_bull' in df.columns else np.zeros(n)
    is_running_s_arr  = pd.to_numeric(df['is_running_bear'], errors='coerce').fillna(0.0).values if 'is_running_bear' in df.columns else np.zeros(n)

    # Jendela pasca-breakout (re-entry yang terjadi dalam 20 candle setelah breakout dari squeeze adalah habitat primer Runner)
    recent_brk_b = pd.Series(is_breakout_b_arr).rolling(20, min_periods=1).max().fillna(0).values
    recent_brk_s = pd.Series(is_breakout_s_arr).rolling(20, min_periods=1).max().fillna(0).values

    # Habitat Runner: Breakout dari Squeeze (recent), Running Trend CSM/EMA, atau BB Mengembang
    is_runner_habitat = (
        (is_breakout_b_arr == 1) | (is_breakout_s_arr == 1) |
        (recent_brk_b == 1)      | (recent_brk_s == 1) |
        (is_running_b_arr == 1)  | (is_running_s_arr == 1) |
        ((is_bb_exp_arr == 1) & (is_bb_sq_arr == 0))
    )

    # Habitat Hit & Run (Normal): Sideways / Squeeze / Reversal Ekstrem Band
    is_normal_habitat = (is_bb_sq_arr == 1) | (~is_runner_habitat)

    labels_normal  = np.zeros(n, dtype=np.int8)
    labels_runner  = np.zeros(n, dtype=np.int8)
    setup_dir_arr  = np.zeros(n, dtype=np.int8)
    mfe_r_arr      = np.zeros(n, dtype=np.float32)
    trigger_scores = np.zeros(n, dtype=np.float32)
    frac_horizons  = np.zeros(n, dtype=np.int16)

    for i in range(n):
        atr_i = float(atrs[i]) if (not np.isnan(atrs[i]) and atrs[i] > 0) else 0.001
        if np.isnan(lwma_low_zone[i]) or np.isnan(lwma_high_zone[i]):
            continue

        buf = profile.zone_buffer_ratio * atr_i
        eval_buy  = (lows[i]  <= lwma_low_zone[i]  + buf)
        eval_sell = (highs[i] >= lwma_high_zone[i] - buf)

        # Filter Zon Zero Loss (ZZL) Wajib jika diatur pada profil instrumen (misal XAUUSD)
        if profile.mandate_zzl:
            eval_buy = eval_buy and (closes[i] >= ema50[i]) and (sma20[i] >= ema50[i])
            eval_sell = eval_sell and (closes[i] <= ema50[i]) and (sma20[i] <= ema50[i])

        # Anti Counter-Trend & Squeeze Extreme Guard
        eval_buy  = eval_buy and (forbid_buy[i] == 0) and (sq_buy_ok[i] == 1)
        eval_sell = eval_sell and (forbid_sell[i] == 0) and (sq_sell_ok[i] == 1)

        if not eval_buy and not eval_sell:
            continue

        # Tentukan setup direction tunggal
        if eval_buy and not eval_sell:
            setup_dir_arr[i] = 1
        elif eval_sell and not eval_buy:
            setup_dir_arr[i] = 2
        elif eval_buy and eval_sell:
            setup_dir_arr[i] = 1 if closes[i] >= ema50[i] else 2

        entry_price = closes[i]
        struct_tol  = struct_buf_ratio * atr_i

        # --- SL Distance (konsisten dengan profile: profile.sl_atr_mult * ATR) ---
        sl_dist_i = max(0.4 * atr_i, min(2.5 * atr_i, profile.sl_atr_mult * atr_i))

        # ---------------------------------------------------------------
        # BUY SETUP
        # ---------------------------------------------------------------
        if eval_buy:
            t_score = _find_trigger_score(
                is_csa_buy, is_csak_buy, is_csm_buy, body_sizes, atrs, i
            )
            trigger_scores[i] = max(trigger_scores[i], t_score)

            fc = int(min(3, max(0, round(float(frac_buy[i])))))
            horizon = HORIZON_BY_FRACTAL.get(fc, 60)
            frac_horizons[i] = horizon

            hard_sl  = entry_price - sl_dist_i
            max_mfe  = 0.0
            consec   = 0
            secured  = False
            invalidated = False

            for j in range(i + 1, min(i + horizon + 1, n)):
                c_c = closes[j]; c_l = lows[j]; c_h = highs[j]
                mid = sma20[j]; e50 = ema50[j]; l_bb = bb_lower[j]

                # --- Invalidation ---
                if c_l <= hard_sl:
                    invalidated = True
                    break
                if c_c < l_bb and not secured:
                    invalidated = True
                    break
                base = min(mid, e50) if e50 > 0 else mid
                if c_c < (base - struct_tol):
                    consec += 1
                    if consec >= 2 and not secured:
                        invalidated = True
                        break
                else:
                    consec = 0

                # --- MFE tracking ---
                excursion_r = (c_h - entry_price) / sl_dist_i
                if excursion_r > max_mfe:
                    max_mfe = excursion_r

                # Secured breakeven ketika hit >= breakeven_r (default 1.0R)
                if not secured and excursion_r >= profile.breakeven_r:
                    secured = True

                # Early exit if we already captured max_runner_rr
                if max_mfe >= max_runner_rr:
                    break

            if not invalidated and t_score > 0:
                mfe_r_arr[i] = max(mfe_r_arr[i], float(max_mfe))
                if max_mfe >= profile.rr_normal and is_normal_habitat[i]:
                    labels_normal[i] = 1
                if max_mfe >= profile.rr_runner and is_runner_habitat[i]:
                    labels_runner[i] = 1

        # ---------------------------------------------------------------
        # SELL SETUP
        # ---------------------------------------------------------------
        if eval_sell:
            t_score = _find_trigger_score(
                is_csa_sell, is_csak_sell, is_csm_sell, body_sizes, atrs, i
            )
            trigger_scores[i] = max(trigger_scores[i], t_score)

            fc = int(min(3, max(0, round(float(frac_sell[i])))))
            horizon = HORIZON_BY_FRACTAL.get(fc, 60)
            frac_horizons[i] = max(frac_horizons[i], horizon)

            hard_sl  = entry_price + sl_dist_i
            max_mfe  = 0.0
            consec   = 0
            secured  = False
            invalidated = False

            for j in range(i + 1, min(i + horizon + 1, n)):
                c_c = closes[j]; c_l = lows[j]; c_h = highs[j]
                mid = sma20[j]; e50 = ema50[j]; t_bb = bb_upper[j]

                # --- Invalidation ---
                if c_h >= hard_sl:
                    invalidated = True
                    break
                if c_c > t_bb and not secured:
                    invalidated = True
                    break
                base = max(mid, e50) if e50 > 0 else mid
                if c_c > (base + struct_tol):
                    consec += 1
                    if consec >= 2 and not secured:
                        invalidated = True
                        break
                else:
                    consec = 0

                # --- MFE tracking ---
                excursion_r = (entry_price - c_l) / sl_dist_i
                if excursion_r > max_mfe:
                    max_mfe = excursion_r

                # Secured breakeven ketika hit >= breakeven_r (default 1.0R)
                if not secured and excursion_r >= profile.breakeven_r:
                    secured = True

                if max_mfe >= max_runner_rr:
                    break

            if not invalidated and t_score > 0:
                cur = mfe_r_arr[i]
                mfe_r_arr[i] = max(cur, float(max_mfe))
                if max_mfe >= profile.rr_normal and is_normal_habitat[i]:
                    labels_normal[i] = 1
                if max_mfe >= profile.rr_runner and is_runner_habitat[i]:
                    labels_runner[i] = 1

    df['setup_dir']       = setup_dir_arr       # 1 = Buy, 2 = Sell, 0 = Inactive
    df['Target_Normal']   = labels_normal.astype(int)
    df['Target_Runner']   = labels_runner.astype(int)
    df['max_mfe_r']       = mfe_r_arr           # label regresi kontinu (opsional)
    df['trigger_score_i'] = trigger_scores       # skor trigger saat candle ini (fitur informatif)
    df['fractal_horizon'] = frac_horizons        # horizon yang dipakai (diagnostik)
    return df
