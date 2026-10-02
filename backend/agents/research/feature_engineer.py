import logging
import numpy as np
import pandas as pd
from typing import List, Set
from utils.indicators import calculate_atr

logger = logging.getLogger(__name__)

# Kolom mentah absolut, target masa depan, atau identifier yang DILARANG masuk ke dalam model features
FORBIDDEN_BASE_COLS = [
    'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume',
    'symbol', 'time', 'timestamp', 'datetime', 'date', 'id', 'setup_dir',
    'max_mfe_r', 'forward_mfe_r', 'forward_mfe', 'mfe', 'fractal_horizon',
    'Target_Normal', 'Target_Runner', 'Target_Profit', 'Target_Buy', 'Target_Sell',
    'Target_Class', 'Target', 'target', 'pnl', 'profit', 'gross_profit',
    'sma_20', 'bb_upper', 'bb_lower', 'ema_50',
    'lwma_5_high', 'lwma_10_high', 'lwma_5_low', 'lwma_10_low',
    'SMA_20', 'BB_Upper', 'BB_Lower', 'EMA_50',
    'LWMA_5_High', 'LWMA_10_High', 'LWMA_5_Low', 'LWMA_10_Low',
    # TD-08: Pruning multikolinearitas ekstrem (> 0.98) jarak mentah Open/Close terhadap 4 garis LWMA
    'dist_open_lwma_5_high', 'dist_open_lwma_10_high', 'dist_open_lwma_5_low', 'dist_open_lwma_10_low',
    'dist_close_lwma_10_high', 'dist_close_lwma_10_low'
]


def add_normalized_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ekstraksi Fitur Berbasis Jarak BBMA, Momentum Open-Close, dan Arah Candle.
    Model 100% TIDAK BELAJAR DARI HARGA NOMINAL, melainkan dari:
    1. Jarak harga (Open, Close, High, Low) terhadap seluruh indikator BBMA (ATR-normalized).
    2. 4 garis LWMA terpisah: LWMA 5 High, LWMA 10 High, LWMA 5 Low, LWMA 10 Low.
    3. Momentum candle dari jarak Open dan Close (mengidentifikasi panjang momentum).
    4. Arah candle (bullish vs bearish).
    5. Geometri & volatilitas Bollinger Bands serta EMA 50.
    6. Lonjakan volume transaksi relatif.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # Pastikan nama kolom standar
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
        if old_c in df.columns and new_c not in df.columns:
            df[new_c] = df[old_c]

    # Pastikan ATR tersedia untuk normalisasi skala
    if 'ATR_14' in df.columns and not df['ATR_14'].isna().all():
        atr_series = df['ATR_14']
    elif 'atr_14' in df.columns and not df['atr_14'].isna().all():
        atr_series = df['atr_14']
    else:
        atr_series = calculate_atr(df, 14)
    df['ATR_14'] = atr_series
    df['atr_14'] = atr_series
    atr = np.maximum(pd.to_numeric(atr_series, errors='coerce').fillna(0.01).values, 1e-4)

    # Convert kolom-kolom harga
    close_s = pd.to_numeric(df['close'], errors='coerce').fillna(0.0)
    open_s = pd.to_numeric(df['open'], errors='coerce').fillna(close_s)
    high_s = pd.to_numeric(df['high'], errors='coerce').fillna(close_s)
    low_s = pd.to_numeric(df['low'], errors='coerce').fillna(close_s)

    c = close_s.values
    o = open_s.values
    h = high_s.values
    l = low_s.values

    # Indikator BBMA & 4 Garis Terpisah LWMA
    sma20_col = df['sma_20'] if 'sma_20' in df.columns else close_s
    sma20 = pd.to_numeric(sma20_col, errors='coerce').fillna(close_s).values

    atr_s = pd.Series(atr, index=df.index)
    bb_u_col = df['bb_upper'] if 'bb_upper' in df.columns else (close_s + 2 * atr_s)
    bb_u = pd.to_numeric(bb_u_col, errors='coerce').fillna(close_s + 2 * atr_s).values

    bb_l_col = df['bb_lower'] if 'bb_lower' in df.columns else (close_s - 2 * atr_s)
    bb_l = pd.to_numeric(bb_l_col, errors='coerce').fillna(close_s - 2 * atr_s).values

    ema50_col = df['ema_50'] if 'ema_50' in df.columns else close_s
    ema50 = pd.to_numeric(ema50_col, errors='coerce').fillna(close_s).values

    lw5h_col = df['lwma_5_high'] if 'lwma_5_high' in df.columns else high_s
    lw5h = pd.to_numeric(lw5h_col, errors='coerce').fillna(high_s).values

    lw10h_col = df['lwma_10_high'] if 'lwma_10_high' in df.columns else high_s
    lw10h = pd.to_numeric(lw10h_col, errors='coerce').fillna(high_s).values

    lw5l_col = df['lwma_5_low'] if 'lwma_5_low' in df.columns else low_s
    lw5l = pd.to_numeric(lw5l_col, errors='coerce').fillna(low_s).values

    lw10l_col = df['lwma_10_low'] if 'lwma_10_low' in df.columns else low_s
    lw10l = pd.to_numeric(lw10l_col, errors='coerce').fillna(low_s).values

    # =========================================================================
    # 1. MOMENTUM OPEN-CLOSE & ARAH CANDLE (BULLISH vs BEARISH)
    # =========================================================================
    # Jarak Close - Open dinormalisasi: Positif = Bullish, Negatif = Bearish
    # Nilai absolut besar = Momentum sangat panjang (Breakout / Marubozu)
    body_dist = (c - o) / atr
    df['feat_candle_momentum'] = body_dist
    df['feat_is_bullish'] = np.where(c >= o, 1.0, -1.0)
    
    # Kepadatan body candle terhadap full range (conviction)
    candle_range = np.maximum(h - l, 1e-5)
    df['feat_body_range_ratio'] = np.abs(c - o) / candle_range

    # Ekor atas dan ekor bawah (rejection wick)
    df['feat_upper_wick'] = (h - np.maximum(o, c)) / atr
    df['feat_lower_wick'] = (np.minimum(o, c) - l) / atr

    # Akumulasi momentum multi-candle (Sustained Momentum vs Exhaustion)
    df['feat_momentum_3_bars'] = pd.Series(body_dist, index=df.index).rolling(3, min_periods=1).sum().fillna(0.0).values
    df['feat_momentum_5_bars'] = pd.Series(body_dist, index=df.index).rolling(5, min_periods=1).sum().fillna(0.0).values
    
    # Lonjakan momentum relatif terhadap rata-rata 10 candle terakhir
    avg_body_10 = pd.Series(np.abs(body_dist), index=df.index).rolling(10, min_periods=1).mean().replace(0, 1.0).values
    df['feat_momentum_surge'] = np.clip(np.abs(body_dist) / avg_body_10, 0.0, 10.0)

    # =========================================================================
    # 2. JARAK HARGA DARI INDIKATOR BBMA (CLOSE & OPEN)
    # =========================================================================
    # Jarak Close terhadap Mid BB, Top BB, Low BB, EMA 50
    df['dist_close_sma20'] = (c - sma20) / atr
    df['dist_close_bb_upper'] = (c - bb_u) / atr
    df['dist_close_bb_lower'] = (c - bb_l) / atr
    df['dist_close_ema50'] = (c - ema50) / atr

    # Jarak Open terhadap Mid BB, Top BB, Low BB, EMA 50
    df['dist_open_sma20'] = (o - sma20) / atr
    df['dist_open_bb_upper'] = (o - bb_u) / atr
    df['dist_open_bb_lower'] = (o - bb_l) / atr
    df['dist_open_ema50'] = (o - ema50) / atr

    # =========================================================================
    # 3. FITUR ORTOGONAL LWMA (CENTER DISTANCE, CHANNEL WIDTH, SKEWNESS)
    # =========================================================================
    lwma_mid = (lw5h + lw10h + lw5l + lw10l) / 4.0
    lwma_ch_width = np.maximum((lw5h + lw10h) / 2.0 - (lw5l + lw10l) / 2.0, 1e-4)

    # Jarak harga Close ke pusat channel LWMA (Center Distance Ratio)
    df['feat_lwma_center_dist'] = (c - lwma_mid) / atr
    # Lebar channel LWMA ternormalisasi
    df['feat_lwma_channel_width'] = lwma_ch_width / atr
    # Rasio ekspansi channel LWMA terhadap lebar Bollinger Bands
    df['feat_lwma_channel_expansion'] = (lwma_ch_width / atr) / np.maximum((bb_u - bb_l) / atr, 0.1)
    # Asimetri posisi harga Close di dalam channel LWMA (Skewness: +1 dekat atap, -1 dekat dasar)
    df['feat_lwma_skew'] = ((lw5h - c) - (c - lw10l)) / lwma_ch_width

    # Jarak batas luar LWMA terhadap Close
    df['dist_close_lwma_5_high'] = (c - lw5h) / atr
    df['dist_close_lwma_5_low'] = (c - lw5l) / atr
    df['dist_close_lwma_10_high'] = (c - lw10h) / atr
    df['dist_close_lwma_10_low'] = (c - lw10l) / atr

    # Penetrasi Ekstrem High dan Low terhadap Bollinger Bands & LWMA
    df['dist_high_bb_upper'] = (h - bb_u) / atr
    df['dist_low_bb_lower'] = (l - bb_l) / atr
    df['dist_high_lwma_5_high'] = (h - lw5h) / atr
    df['dist_low_lwma_5_low'] = (l - lw5l) / atr

    # =========================================================================
    # 4. RELASI ANTAR GARIS INDIKATOR (GEOMETRI BBMA)
    # =========================================================================
    # Spread antara MA 5 dan MA 10 High/Low
    df['feat_lwma_spread_high'] = (lw5h - lw10h) / atr
    df['feat_lwma_spread_low'] = (lw5l - lw10l) / atr
    df['feat_lwma_channel_width'] = (lw5h - lw5l) / atr

    # Sinyal Extrem Matematis: MA 5 tembus keluar dari Bollinger Bands
    df['feat_extrem_sell_depth'] = (lw5h - bb_u) / atr
    df['feat_extrem_buy_depth'] = (bb_l - lw5l) / atr

    # Lebar Bollinger Bands (Volatilitas) dan Slopenya (Squeeze vs Expanding)
    bb_width_norm = (bb_u - bb_l) / np.maximum(sma20, 1e-4)
    df['feat_bb_width_norm'] = bb_width_norm
    df['feat_bb_width_slope'] = (pd.Series(bb_width_norm, index=df.index) - pd.Series(bb_width_norm, index=df.index).shift(3)).fillna(0.0).values

    # Kemiringan Mid BB dan Trend EMA 50
    df['feat_sma20_slope'] = (pd.Series(sma20, index=df.index) - pd.Series(sma20, index=df.index).shift(3)).fillna(0.0).values / atr
    df['feat_ema50_slope'] = (pd.Series(ema50, index=df.index) - pd.Series(ema50, index=df.index).shift(3)).fillna(0.0).values / atr
    df['feat_dist_sma20_ema50'] = (sma20 - ema50) / atr

    # =========================================================================
    # 5. DINAMIKA VOLUME TRANSAKSI RELATIF
    # =========================================================================
    if 'tick_volume' in df.columns:
        vol = pd.to_numeric(df['tick_volume'], errors='coerce').fillna(1.0)
        vol_ma = vol.rolling(20, min_periods=5).mean().fillna(vol).replace(0, 1.0)
        df['feat_relative_volume'] = np.clip(vol.values / vol_ma.values, 0.1, 10.0)
        df['feat_volume_change'] = (vol.values - vol.shift(1).fillna(vol).values) / np.maximum(vol.shift(1).fillna(vol).values, 1.0)

    # Forward fill dan isi nilai NaN residual dengan 0.0
    df.ffill(inplace=True)
    df.fillna(0.0, inplace=True)
    return df


def extract_and_lock_features(df: pd.DataFrame, mode: str = "unified") -> List[str]:
    """
    Mengunci daftar fitur numerik yang valid (bebas dari harga nominal, identifier, dan future data leakage).
    """
    candidate_features = []
    for col in df.columns:
        if col in FORBIDDEN_BASE_COLS or col.startswith('_'):
            continue
        col_l = col.lower()
        if any(kw in col_l for kw in ['target', 'mfe', 'forward', 'future', 'pnl', 'profit', 'horizon', 'return_']):
            continue
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            candidate_features.append(col)
        else:
            coerced = pd.to_numeric(df[col], errors='coerce')
            if not coerced.isna().all():
                candidate_features.append(col)

    logger.info(f"[FEATURE ENGINEER] Terkunci {len(candidate_features)} fitur tanpa harga nominal: {candidate_features}")
    return candidate_features
