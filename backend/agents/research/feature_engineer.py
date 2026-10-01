import logging
import numpy as np
import pandas as pd
from typing import List, Set
from utils.indicators import calculate_atr, calculate_bbma_sequence_features, calculate_fractal_origin

logger = logging.getLogger(__name__)

RAW_NON_STATIONARY = [
    'dist_Close_EMA50', 'dist_Close_SMA20', 'BB_Width', 'dist_LWMA_High_BB_Upper',
    'dist_Close_LWMA_Low', 'dist_Low_LWMA_Low', 'dist_Close_LWMA_High', 'dist_High_LWMA_High',
    'SMA_20_Slope', 'BB_Width_Slope', 'LWMA_Crossover_High', 'LWMA_Crossover_Low',
    'upper_wick', 'lower_wick', 'body_size'
]

# Kolom fitur baru berbasis sekuens dan fraktal asal (dimensionless / tidak memerlukan
# normalisasi ATR karena sudah dinormalisasi di dalam fungsi calculate_* masing-masing)
SEQUENCE_FRACTAL_PASSTHROUGH = [
    # Bars-since features (skala candle, bukan harga)
    'bars_since_csa_buy',   'bars_since_csa_sell',
    'bars_since_csak_buy',  'bars_since_csak_sell',
    'bars_since_csm_buy',   'bars_since_csm_sell',
    'bars_since_extrem_buy','bars_since_extrem_sell',
    # Freshness decay scores (0..1)
    'freshness_csa_buy',    'freshness_csa_sell',
    'freshness_csak_buy',   'freshness_csak_sell',
    'freshness_csm_buy',    'freshness_csm_sell',
    # Trigger momentum ratios (dimensionless body/ATR)
    'trigger_momentum_csa_buy',   'trigger_momentum_csa_sell',
    'trigger_momentum_csak_buy',  'trigger_momentum_csak_sell',
    'trigger_momentum_csm_buy',   'trigger_momentum_csm_sell',
    # Composite trigger scores
    'trigger_score_buy',    'trigger_score_sell',
    # Room-to-BB (dimensionless, ATR-normalized)
    'room_to_bb_upper',     'room_to_bb_lower',
    # MHV likelihood
    'mhv_likelihood',
    # Body rejection quality
    'reentry_quality_buy',  'reentry_quality_sell',
    # Fractal origin (count 0..3)
    'fractal_origin_buy',   'fractal_origin_sell',
    # Fractal capacity estimate
    'fractal_capacity_buy', 'fractal_capacity_sell',
    # Per-TF Re-entry flags
    'is_reentry_buy_base',  'is_reentry_sell_base',
    'is_reentry_buy_setup', 'is_reentry_sell_setup',
    'is_reentry_buy_trend', 'is_reentry_sell_trend',
    # ATR cross-TF ratios (dimensionless)
    'atr_ratio_setup_base', 'atr_ratio_trend_base',
]

FORBIDDEN_BASE_COLS = [
    'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume',
    'symbol', 'time', 'timestamp', 'datetime', 'date', 'id', 'setup_dir',
    'max_mfe_r', 'fractal_horizon', 'Target_Normal', 'Target_Runner'
] + RAW_NON_STATIONARY


def add_normalized_features(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    df = df.copy()
    regime_cols = ('BB_Upper', 'forbid_buy', 'is_CSA_Buy', 'is_breakout_bull', 'is_running_bull', 'is_bb_squeeze', 'is_bb_expanding')
    if any(c not in df.columns or (c in df.columns and df[c].isna().all()) for c in regime_cols):
        from utils.indicators import calculate_bbma
        df = calculate_bbma(df)

    atr_series = df['ATR_14'] if 'ATR_14' in df.columns else calculate_atr(df, 14)
    atr_safe = np.maximum(pd.to_numeric(atr_series, errors='coerce').fillna(0.01).values, 1e-4)

    for col in RAW_NON_STATIONARY:
        if col in df.columns:
            val = pd.to_numeric(df[col], errors='coerce').fillna(0.0).values
            df[f'norm_{col}'] = val / atr_safe

    # Normalisasi MTF (_setup, _trend, _m5, _m15, _h1, _h4)
    for tf in ['_setup', '_trend', '_m5', '_m15', '_h1', '_h4']:
        atr_tf_col = f'ATR_14{tf}'
        if atr_tf_col in df.columns:
            atr_tf_safe = np.maximum(pd.to_numeric(df[atr_tf_col], errors='coerce').fillna(0.01).values, 1e-4)
            for col in ['dist_Close_EMA50', 'dist_Close_SMA20', 'BB_Width', 'dist_Close_LWMA_Low', 'dist_Close_LWMA_High', 'body_size']:
                full_col = f"{col}{tf}"
                if full_col in df.columns:
                    v = pd.to_numeric(df[full_col], errors='coerce').fillna(0.0).values
                    df[f"norm_{full_col}"] = v / atr_tf_safe

    # --- CROSS-TIMEFRAME CONFLUENCE & AUTONOMOUS ALIGNMENT ---
    # Memungkinkan model AI secara mandiri menemukan korelasi / pengaruh antar timeframe per pair
    setup_col = 'dist_Close_EMA50_setup' if 'dist_Close_EMA50_setup' in df.columns else ('dist_Close_EMA50_m5' if 'dist_Close_EMA50_m5' in df.columns else None)
    trend_col = 'dist_Close_EMA50_trend' if 'dist_Close_EMA50_trend' in df.columns else ('dist_Close_EMA50_m15' if 'dist_Close_EMA50_m15' in df.columns else None)
    
    if 'dist_Close_EMA50' in df.columns and setup_col is not None and setup_col in df.columns:
        base_dist = pd.to_numeric(df['dist_Close_EMA50'], errors='coerce').fillna(0.0).values
        setup_s = pd.to_numeric(df[setup_col], errors='coerce').fillna(0.0)
        trend_s = pd.to_numeric(df[trend_col], errors='coerce').fillna(setup_s) if (trend_col and trend_col in df.columns) else setup_s
        base_bull = (base_dist > 0).astype(float)
        setup_bull = (setup_s.values > 0).astype(float)
        trend_bull = (trend_s.values > 0).astype(float)
        df['mtf_trend_alignment'] = (base_bull + setup_bull + trend_bull - 1.5) / 1.5

    if 'adx' in df.columns:
        adx_setup_col = 'adx_setup' if 'adx_setup' in df.columns else ('adx_m5' if 'adx_m5' in df.columns else None)
        if adx_setup_col is not None and adx_setup_col in df.columns:
            base_adx = pd.to_numeric(df['adx'], errors='coerce').fillna(20.0).values
            setup_adx = pd.to_numeric(df[adx_setup_col], errors='coerce').fillna(20.0).values
            df['mtf_adx_momentum_ratio'] = base_adx / np.maximum(setup_adx, 1.0)

    # --- 1. FITUR SESI PASAR & SIKLIKAL TEMPORAL ---
    try:
        dt_idx = pd.to_datetime(df['time'] if 'time' in df.columns else df.index, errors='coerce')
        if hasattr(dt_idx, 'hour'):
            hours = dt_idx.hour.to_numpy(dtype=float)
            dows = dt_idx.dayofweek.to_numpy(dtype=float) if hasattr(dt_idx, 'dayofweek') else np.zeros(len(df))
            df['sin_hour'] = np.sin(2.0 * np.pi * hours / 24.0)
            df['cos_hour'] = np.cos(2.0 * np.pi * hours / 24.0)
            df['sin_dow'] = np.sin(2.0 * np.pi * dows / 5.0)
            df['cos_dow'] = np.cos(2.0 * np.pi * dows / 5.0)
            df['is_london_session'] = ((hours >= 7) & (hours < 16)).astype(float)
            df['is_ny_session'] = ((hours >= 12) & (hours < 21)).astype(float)
            df['is_overlap_session'] = ((hours >= 12) & (hours < 16)).astype(float)
            df['is_asian_session'] = ((hours >= 0) & (hours < 7)).astype(float)
    except Exception:
        pass

    # --- 2. VOLATILITY COMPRESSION (BOLLINGER SQUEEZE PERCENTILE) ---
    if 'BB_Width' in df.columns:
        bb_w = pd.to_numeric(df['BB_Width'], errors='coerce').fillna(0.0)
        df['bb_width_percentile'] = bb_w.rolling(100, min_periods=10).rank(pct=True).fillna(0.5).values
        bb_ma = bb_w.rolling(50, min_periods=10).mean().replace(0, 1e-4).fillna(1.0).values
        df['bb_squeeze_ratio'] = bb_w.values / bb_ma

    # --- 3. ATR VOLATILITY BURST RATIO ---
    atr_s_clean = pd.Series(atr_safe, index=df.index)
    atr_100 = atr_s_clean.rolling(100, min_periods=10).mean().fillna(atr_s_clean).values
    df['norm_atr_ratio'] = atr_safe / np.maximum(atr_100, 1e-4)

    # --- 4. ANATOMI CANDLESTICK REJECTION ---
    if 'high' in df.columns and 'low' in df.columns:
        candle_range = np.maximum((pd.to_numeric(df['high'], errors='coerce') - pd.to_numeric(df['low'], errors='coerce')).fillna(1e-4).values, 1e-4)
        if 'upper_wick' in df.columns:
            df['upper_wick_ratio'] = pd.to_numeric(df['upper_wick'], errors='coerce').fillna(0.0).values / candle_range
        if 'lower_wick' in df.columns:
            df['lower_wick_ratio'] = pd.to_numeric(df['lower_wick'], errors='coerce').fillna(0.0).values / candle_range
        if 'body_size' in df.columns:
            df['body_ratio'] = pd.to_numeric(df['body_size'], errors='coerce').fillna(0.0).values / candle_range

    # --- 5. RELATIVE VOLUME ---
    if 'tick_volume' in df.columns:
        vol = pd.to_numeric(df['tick_volume'], errors='coerce').fillna(1.0)
        vol_ma = vol.rolling(20, min_periods=5).mean().fillna(vol).replace(0, 1.0)
        df['norm_relative_volume'] = np.clip(vol.values / vol_ma.values, 0.1, 10.0)

    # --- 6. FITUR TOPOGRAFI & REGIME BOLLINGER BANDS (ML Alpha) ---
    if 'is_running_bull' in df.columns:
        df['feat_is_running_bull'] = pd.to_numeric(df['is_running_bull'], errors='coerce').fillna(0.0).values.astype(float)
    if 'is_running_bear' in df.columns:
        df['feat_is_running_bear'] = pd.to_numeric(df['is_running_bear'], errors='coerce').fillna(0.0).values.astype(float)
    if 'is_bb_squeeze' in df.columns:
        df['feat_is_bb_squeeze'] = pd.to_numeric(df['is_bb_squeeze'], errors='coerce').fillna(0.0).values.astype(float)
    if 'is_breakout_bull' in df.columns:
        df['feat_is_breakout_bull'] = pd.to_numeric(df['is_breakout_bull'], errors='coerce').fillna(0.0).values.astype(float)
    if 'is_breakout_bear' in df.columns:
        df['feat_is_breakout_bear'] = pd.to_numeric(df['is_breakout_bear'], errors='coerce').fillna(0.0).values.astype(float)
    if 'BB_Width_Slope' in df.columns:
        df['norm_bb_width_slope'] = pd.to_numeric(df['BB_Width_Slope'], errors='coerce').fillna(0.0).values / atr_safe
    if 'SMA_20_Slope' in df.columns:
        df['norm_sma20_slope'] = pd.to_numeric(df['SMA_20_Slope'], errors='coerce').fillna(0.0).values / atr_safe

    # --- DIRECTION-ALIGNED SETUP FEATURES ---
    if 'setup_dir' not in df.columns:
        low_s = pd.to_numeric(df['low'], errors='coerce').fillna(0.0)
        high_s = pd.to_numeric(df['high'], errors='coerce').fillna(0.0)
        close_s = pd.to_numeric(df['close'], errors='coerce').fillna(0.0)
        lwma_5_l = pd.to_numeric(df['LWMA_5_Low'], errors='coerce').fillna(low_s).values if 'LWMA_5_Low' in df.columns else low_s.values
        lwma_10_l = pd.to_numeric(df['LWMA_10_Low'], errors='coerce').fillna(low_s).values if 'LWMA_10_Low' in df.columns else low_s.values
        lwma_5_h = pd.to_numeric(df['LWMA_5_High'], errors='coerce').fillna(high_s).values if 'LWMA_5_High' in df.columns else high_s.values
        lwma_10_h = pd.to_numeric(df['LWMA_10_High'], errors='coerce').fillna(high_s).values if 'LWMA_10_High' in df.columns else high_s.values

        lwma_low_zone = np.maximum(lwma_5_l, lwma_10_l)
        lwma_high_zone = np.minimum(lwma_5_h, lwma_10_h)
        atr_vals = pd.to_numeric(df['ATR_14'], errors='coerce').fillna(0.001).values if 'ATR_14' in df.columns else np.full(len(df), 0.001)
        buffer = 0.25 * atr_vals

        forbid_b = pd.to_numeric(df['forbid_buy'], errors='coerce').fillna(0.0).values if 'forbid_buy' in df.columns else np.zeros(len(df))
        forbid_s = pd.to_numeric(df['forbid_sell'], errors='coerce').fillna(0.0).values if 'forbid_sell' in df.columns else np.zeros(len(df))
        sq_b = pd.to_numeric(df['is_squeeze_buy_allowed'], errors='coerce').fillna(1.0).values if 'is_squeeze_buy_allowed' in df.columns else np.ones(len(df))
        sq_s = pd.to_numeric(df['is_squeeze_sell_allowed'], errors='coerce').fillna(1.0).values if 'is_squeeze_sell_allowed' in df.columns else np.ones(len(df))

        low_vals = low_s.values
        high_vals = high_s.values
        close_vals = close_s.values

        reentry_buy_mask = (low_vals <= (lwma_low_zone + buffer)) & (forbid_b == 0) & (sq_b == 1)
        reentry_sell_mask = (high_vals >= (lwma_high_zone - buffer)) & (forbid_s == 0) & (sq_s == 1)

        if 'EMA_50' in df.columns and 'SMA_20' in df.columns:
            ema50_vals = pd.to_numeric(df['EMA_50'], errors='coerce').fillna(close_s).values
            sma20_vals = pd.to_numeric(df['SMA_20'], errors='coerce').fillna(close_s).values
            reentry_buy_mask = reentry_buy_mask & (close_vals >= ema50_vals) & (sma20_vals >= ema50_vals)
            reentry_sell_mask = reentry_sell_mask & (close_vals <= ema50_vals) & (sma20_vals <= ema50_vals)

        df['setup_dir'] = np.where(reentry_buy_mask, 1, np.where(reentry_sell_mask, 2, 0))

    s_dir = pd.to_numeric(df['setup_dir'], errors='coerce').fillna(0).values
    df['is_buy_setup'] = (s_dir == 1).astype(float)
    if 'lower_wick_ratio' in df.columns and 'upper_wick_ratio' in df.columns:
        df['norm_rejection_wick'] = np.where(s_dir == 1, df['lower_wick_ratio'], df['upper_wick_ratio'])
        df['norm_adverse_wick'] = np.where(s_dir == 1, df['upper_wick_ratio'], df['lower_wick_ratio'])
    if 'norm_dist_Close_EMA50' in df.columns:
        df['aligned_dist_ema50'] = np.where(s_dir == 1, df['norm_dist_Close_EMA50'], -df['norm_dist_Close_EMA50'])
    if 'norm_dist_Close_SMA20' in df.columns:
        df['aligned_dist_sma20'] = np.where(s_dir == 1, df['norm_dist_Close_SMA20'], -df['norm_dist_Close_SMA20'])

    # --- 7. FITUR SEKUENSIAL BBMA (n-candle history) ---
    # Menghitung berapa candle lalu muncul CSA/CSAK/CSM, seberapa kuat,
    # ruang gerak ke BB seberang, dan kualitas body rejection candle saat ini.
    try:
        df = calculate_bbma_sequence_features(df, lookback=30)
    except Exception as e_seq:
        logger.debug(f"Gagal hitung BBMA sequence features: {e_seq}")

    # --- 8. FRACTAL ORIGIN DETECTION (posisi Re-entry di multi-TF) ---
    # Mendeteksi di TF mana (base/setup/trend) harga sedang menyentuh zona
    # Re-entry LWMA secara simultan. Semakin besar TF yang aktif = energi lebih besar.
    try:
        df = calculate_fractal_origin(df)
    except Exception as e_frac:
        logger.debug(f"Gagal hitung Fractal Origin features: {e_frac}")

    return df


def extract_and_lock_features(df: pd.DataFrame, mode: str = "normal") -> List[str]:
    forbidden_cols: Set[str] = set()
    tf_list = ['', '_setup', '_trend', '_m5', '_m15'] if mode == 'normal' else ['', '_setup', '_trend', '_m5', '_m15', '_h1', '_h4']
    for tf in tf_list:
        for c in FORBIDDEN_BASE_COLS:
            forbidden_cols.add(f"{c}{tf}")
        for c in ['SMA_20', 'BB_Upper', 'BB_Lower', 'EMA_50', 'LWMA_5_High', 'LWMA_10_High', 'LWMA_5_Low', 'LWMA_10_Low']:
            forbidden_cols.add(f"{c}{tf}")

    candidate_features = []
    # Prioritas: sequence & fractal features selalu masuk jika tersedia
    for col in SEQUENCE_FRACTAL_PASSTHROUGH:
        if col in df.columns:
            candidate_features.append(col)

    for col in df.columns:
        if col in candidate_features:  # Sudah masuk dari passthrough
            continue
        if col in forbidden_cols or 'Target' in col or col.startswith('_') or 'mfe' in col.lower() or 'horizon' in col.lower():
            continue
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            candidate_features.append(col)
        else:
            coerced = pd.to_numeric(df[col], errors='coerce')
            if not coerced.isna().all():
                candidate_features.append(col)

    logger.info(f"[RESEARCHER] Locked {len(candidate_features)} regime-invariant features: {candidate_features}")
    return candidate_features
