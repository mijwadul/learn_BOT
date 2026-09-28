import logging
import numpy as np
import pandas as pd
from typing import List, Set
from utils.indicators import calculate_atr

logger = logging.getLogger(__name__)

RAW_NON_STATIONARY = [
    'dist_Close_EMA50', 'dist_Close_SMA20', 'BB_Width', 'dist_LWMA_High_BB_Upper',
    'dist_Close_LWMA_Low', 'dist_Low_LWMA_Low', 'dist_Close_LWMA_High', 'dist_High_LWMA_High',
    'SMA_20_Slope', 'BB_Width_Slope', 'LWMA_Crossover_High', 'LWMA_Crossover_Low',
    'upper_wick', 'lower_wick', 'body_size'
]

FORBIDDEN_BASE_COLS = [
    'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume',
    'symbol', 'time', 'timestamp', 'datetime', 'date', 'id', 'setup_dir'
] + RAW_NON_STATIONARY


def add_normalized_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Menambahkan fitur topografi dan karakteristik candle yang dinormalisasi berbasis ATR (Dimensionless Ratios).
    Diperkaya dengan Institutional Alpha Features:
    1. Sesi & Waktu (London, NY, Asian, Overlap, Sin/Cos Hour & DOW)
    2. Volatilitas & Kompresi (Bollinger Squeeze Percentile & ATR Burst)
    3. Anatomi Rejection Candle (Wick & Body Ratios)
    4. Relative Volume (Tick Volume vs Rolling MA)
    5. Direction-Aligned Symmetric Setup Features
    """
    if df is None or df.empty:
        return df

    df = df.copy()
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
    setup_col = 'dist_Close_EMA50_setup' if 'dist_Close_EMA50_setup' in df.columns else 'dist_Close_EMA50_m5'
    trend_col = 'dist_Close_EMA50_trend' if 'dist_Close_EMA50_trend' in df.columns else 'dist_Close_EMA50_m15'
    
    if 'dist_Close_EMA50' in df.columns and setup_col in df.columns:
        base_bull = (df['dist_Close_EMA50'] > 0).astype(float)
        setup_bull = (df[setup_col] > 0).astype(float)
        trend_bull = (df[trend_col] > 0).astype(float) if trend_col in df.columns else setup_bull
        df['mtf_trend_alignment'] = (base_bull + setup_bull + trend_bull - 1.5) / 1.5

    if 'adx' in df.columns:
        adx_setup_col = 'adx_setup' if 'adx_setup' in df.columns else 'adx_m5'
        if adx_setup_col in df.columns:
            df['mtf_adx_momentum_ratio'] = df['adx'] / np.maximum(df[adx_setup_col], 1.0)

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

    # --- 6. DIRECTION-ALIGNED SETUP FEATURES ---
    if 'setup_dir' not in df.columns:
        lwma_low_zone = np.maximum(df['LWMA_5_Low'].values, df['LWMA_10_Low'].values) if 'LWMA_5_Low' in df.columns else df['low'].values
        lwma_high_zone = np.minimum(df['LWMA_5_High'].values, df['LWMA_10_High'].values) if 'LWMA_5_High' in df.columns else df['high'].values
        atr_vals = df['ATR_14'].values if 'ATR_14' in df.columns else np.full(len(df), 0.001)
        buffer = 0.35 * atr_vals

        reentry_buy_mask = (df['low'].values <= (lwma_low_zone + buffer))
        reentry_sell_mask = (df['high'].values >= (lwma_high_zone - buffer))
        df['setup_dir'] = np.where(reentry_buy_mask, 1, np.where(reentry_sell_mask, 2, 0))

    s_dir = df['setup_dir'].values
    df['is_buy_setup'] = (s_dir == 1).astype(float)
    if 'lower_wick_ratio' in df.columns and 'upper_wick_ratio' in df.columns:
        df['norm_rejection_wick'] = np.where(s_dir == 1, df['lower_wick_ratio'], df['upper_wick_ratio'])
        df['norm_adverse_wick'] = np.where(s_dir == 1, df['upper_wick_ratio'], df['lower_wick_ratio'])
    if 'norm_dist_Close_EMA50' in df.columns:
        df['aligned_dist_ema50'] = np.where(s_dir == 1, df['norm_dist_Close_EMA50'], -df['norm_dist_Close_EMA50'])
    if 'norm_dist_Close_SMA20' in df.columns:
        df['aligned_dist_sma20'] = np.where(s_dir == 1, df['norm_dist_Close_SMA20'], -df['norm_dist_Close_SMA20'])

    return df


def extract_and_lock_features(df: pd.DataFrame, mode: str = "normal") -> List[str]:
    """
    Mengisolasi fitur invarian rezim (regime-invariant features) yang aman untuk generalisasi ML.
    Menghindari non-stationarity harga absolut dan indikator statis.
    """
    forbidden_cols: Set[str] = set()
    tf_list = ['', '_setup', '_trend', '_m5', '_m15'] if mode == 'normal' else ['', '_setup', '_trend', '_m5', '_m15', '_h1', '_h4']
    for tf in tf_list:
        for c in FORBIDDEN_BASE_COLS:
            forbidden_cols.add(f"{c}{tf}")
        for c in ['SMA_20', 'BB_Upper', 'BB_Lower', 'EMA_50', 'LWMA_5_High', 'LWMA_10_High', 'LWMA_5_Low', 'LWMA_10_Low']:
            forbidden_cols.add(f"{c}{tf}")

    candidate_features = []
    for col in df.columns:
        if col in forbidden_cols or 'Target' in col or col.startswith('_'):
            continue
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            candidate_features.append(col)
        else:
            coerced = pd.to_numeric(df[col], errors='coerce')
            if not coerced.isna().all():
                candidate_features.append(col)

    logger.info(f"[RESEARCHER] Locked {len(candidate_features)} regime-invariant features: {candidate_features}")
    return candidate_features
