import pandas as pd
import numpy as np

def calculate_sma(series, length):
    return series.rolling(window=length).mean()

def calculate_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def calculate_lwma(series, length):
    weights = np.arange(1, length + 1)
    return series.rolling(window=length).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)

def calculate_atr(df, length=14):
    df_copy = df.copy()
    df_copy['H-L'] = df_copy['high'] - df_copy['low']
    df_copy['H-PC'] = abs(df_copy['high'] - df_copy['close'].shift(1))
    df_copy['L-PC'] = abs(df_copy['low'] - df_copy['close'].shift(1))
    df_copy['TR'] = df_copy[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    return df_copy['TR'].rolling(window=length).mean()

def calculate_adx(df, length=14):
    df_copy = df.copy()
    df_copy['up_move'] = df_copy['high'] - df_copy['high'].shift(1)
    df_copy['down_move'] = df_copy['low'].shift(1) - df_copy['low']
    
    df_copy['+dm'] = np.where((df_copy['up_move'] > df_copy['down_move']) & (df_copy['up_move'] > 0), df_copy['up_move'], 0.0)
    df_copy['-dm'] = np.where((df_copy['down_move'] > df_copy['up_move']) & (df_copy['down_move'] > 0), df_copy['down_move'], 0.0)
    
    tr = df_copy[['high']].copy()
    tr['H-L'] = df_copy['high'] - df_copy['low']
    tr['H-PC'] = abs(df_copy['high'] - df_copy['close'].shift(1))
    tr['L-PC'] = abs(df_copy['low'] - df_copy['close'].shift(1))
    df_copy['tr'] = tr[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    
    atr = df_copy['tr'].ewm(alpha=1/length, adjust=False).mean()
    plus_di = 100 * (df_copy['+dm'].ewm(alpha=1/length, adjust=False).mean() / atr)
    minus_di = 100 * (df_copy['-dm'].ewm(alpha=1/length, adjust=False).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx.ewm(alpha=1/length, adjust=False).mean()

def calculate_bbma(df):
    """
    Menghitung topografi BBMA berdasarkan spesifikasi:
    - Bollinger Bands (20, 2)
    - EMA (50, Close)
    - LWMA High (5, 10)
    - LWMA Low (5, 10)
    """
    df = df.copy()
    
    # Bollinger Bands
    df['SMA_20'] = calculate_sma(df['close'], 20)
    std = df['close'].rolling(window=20).std()
    df['BB_Upper'] = df['SMA_20'] + (std * 2)
    df['BB_Lower'] = df['SMA_20'] - (std * 2)
    
    # EMA
    df['EMA_50'] = calculate_ema(df['close'], 50)
    
    # LWMA (4 Garis Terpisah)
    df['LWMA_5_High'] = calculate_lwma(df['high'], 5)
    df['LWMA_10_High'] = calculate_lwma(df['high'], 10)
    df['LWMA_5_Low'] = calculate_lwma(df['low'], 5)
    df['LWMA_10_Low'] = calculate_lwma(df['low'], 10)

    # Standard Lowercase Aliases for DB and ML Pipeline
    df['sma_20'] = df['SMA_20']
    df['bb_upper'] = df['BB_Upper']
    df['bb_lower'] = df['BB_Lower']
    df['ema_50'] = df['EMA_50']
    df['lwma_5_high'] = df['LWMA_5_High']
    df['lwma_10_high'] = df['LWMA_10_High']
    df['lwma_5_low'] = df['LWMA_5_Low']
    df['lwma_10_low'] = df['LWMA_10_Low']
    
    # Jarak Topografi
    df['dist_Close_EMA50'] = df['close'] - df['EMA_50']
    df['dist_Close_SMA20'] = df['close'] - df['SMA_20']
    df['BB_Width'] = df['BB_Upper'] - df['BB_Lower']
    df['dist_LWMA_High_BB_Upper'] = df['LWMA_5_High'] - df['BB_Upper']
    
    # Topografi Zona Re-entry LWMA (Low & High)
    lwma_low_zone = np.maximum(df['LWMA_5_Low'], df['LWMA_10_Low'])
    lwma_high_zone = np.minimum(df['LWMA_5_High'], df['LWMA_10_High'])
    df['dist_Close_LWMA_Low'] = df['close'] - lwma_low_zone
    df['dist_Low_LWMA_Low'] = df['low'] - lwma_low_zone
    df['dist_Close_LWMA_High'] = df['close'] - lwma_high_zone
    df['dist_High_LWMA_High'] = df['high'] - lwma_high_zone
    df['is_LWMA_Low_Touch'] = np.where(df['low'] <= lwma_low_zone, 1, 0)
    df['is_LWMA_High_Touch'] = np.where(df['high'] >= lwma_high_zone, 1, 0)
    
    # Kemiringan / Deteksi Sideways (MHV) - Rate of Change (ROC) selama 3 candle
    df['SMA_20_Slope'] = df['SMA_20'] - df['SMA_20'].shift(3)
    df['BB_Width_Slope'] = df['BB_Width'] - df['BB_Width'].shift(3)
    
    # Deteksi Momentum (CSM - Slide 20 & 38)
    df['is_CSM_Buy'] = np.where(df['close'] > df['BB_Upper'], 1, 0)
    df['is_CSM_Sell'] = np.where(df['close'] < df['BB_Lower'], 1, 0)
    
    # Deteksi Extrem BBMA (Slide 21) - MA 5 keluar dari Bollinger Band
    df['is_Extrem_Buy'] = np.where(df['LWMA_5_Low'] < df['BB_Lower'], 1, 0)
    df['is_Extrem_Sell'] = np.where(df['LWMA_5_High'] > df['BB_Upper'], 1, 0)

    # Deteksi Candlestick Arah (CSA) - candle yang menembus MA 5 dan MA 10
    df['is_CSA_Buy'] = np.where(
        (df['close'] > df['LWMA_5_Low']) & (df['close'] > df['LWMA_10_Low']) &
        (df['open'] < df['LWMA_5_Low']),
        1, 0
    )
    df['is_CSA_Sell'] = np.where(
        (df['close'] < df['LWMA_5_High']) & (df['close'] < df['LWMA_10_High']) &
        (df['open'] > df['LWMA_5_High']),
        1, 0
    )

    # Deteksi Candlestick Arah Kukuh (CSAK - Slide 31)
    df['is_CSAK_Buy'] = np.where(
        (df['close'] > df['SMA_20']) & (df['close'] > df['LWMA_5_High']) & (df['close'] > df['LWMA_10_High']) & (df['open'] < df['SMA_20']),
        1, 0
    )
    df['is_CSAK_Sell'] = np.where(
        (df['close'] < df['SMA_20']) & (df['close'] < df['LWMA_5_Low']) & (df['close'] < df['LWMA_10_Low']) & (df['open'] > df['SMA_20']),
        1, 0
    )

    # Kaedah Re-entry Valid BBMA (Slide 33: Body Rejection & No-CSM Filter)
    df['is_Reentry_Buy_Valid'] = np.where(
        (df['low'] <= lwma_low_zone) & (df['close'] >= df['SMA_20']) & (df['close'] <= df['BB_Upper']),
        1, 0
    )
    df['is_Reentry_Sell_Valid'] = np.where(
        (df['high'] >= lwma_high_zone) & (df['close'] <= df['SMA_20']) & (df['close'] >= df['BB_Lower']),
        1, 0
    )

    # Zon Zero Loss (ZZL - Slide 51-56: Setup Win Rate Tertinggi BBMA)
    df['is_ZZL_Buy'] = np.where(
        (df['SMA_20'] >= df['EMA_50']) & (df['close'] >= df['EMA_50']) & (lwma_low_zone >= df['SMA_20']) & (df['is_Reentry_Buy_Valid'] == 1),
        1, 0
    )
    df['is_ZZL_Sell'] = np.where(
        (df['SMA_20'] <= df['EMA_50']) & (df['close'] <= df['EMA_50']) & (lwma_high_zone <= df['SMA_20']) & (df['is_Reentry_Sell_Valid'] == 1),
        1, 0
    )

    # Arah Tren LWMA (Crossover)
    df['LWMA_Crossover_High'] = df['LWMA_5_High'] - df['LWMA_10_High']
    df['LWMA_Crossover_Low'] = df['LWMA_5_Low'] - df['LWMA_10_Low']
    
    # Karakteristik Candlestick (Pola Ekor & Body)
    df['upper_wick'] = df['high'] - np.maximum(df['open'], df['close'])
    df['lower_wick'] = np.minimum(df['open'], df['close']) - df['low']
    df['body_size'] = np.abs(df['close'] - df['open'])
    df['candle_dir'] = np.where(df['close'] >= df['open'], 1, -1)
    
    # Deteksi Pola Engulfing
    df['prev_open'] = df['open'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    
    # Bullish Engulfing: previous is red, current is green, current body engulfs previous
    df['is_Bullish_Engulfing'] = np.where(
        (df['prev_close'] < df['prev_open']) & 
        (df['close'] > df['open']) & 
        (df['close'] >= df['prev_open']) & 
        (df['open'] <= df['prev_close']), 
        1, 0
    )
    
    # Bearish Engulfing: previous is green, current is red, current body engulfs previous
    df['is_Bearish_Engulfing'] = np.where(
        (df['prev_close'] > df['prev_open']) & 
        (df['close'] < df['open']) & 
        (df['close'] <= df['prev_open']) & 
        (df['open'] >= df['prev_close']), 
        1, 0
    )
    
    # Drop temp columns used for engulfing
    df.drop(columns=['prev_open', 'prev_close'], inplace=True)

    # -----------------------------------------------------------------------
    # TOPOGRAFI & REGIME BOLLINGER BANDS (Anti Counter-Trend & Squeeze Shield)
    # -----------------------------------------------------------------------
    # 1. Slope batas BB (Upper & Lower ROC 3 candle)
    df['BB_Upper_Slope'] = df['BB_Upper'] - df['BB_Upper'].shift(3)
    df['BB_Lower_Slope'] = df['BB_Lower'] - df['BB_Lower'].shift(3)

    # 2. Volatilitas & Deteksi Squeeze (BB Mengecil / Menguncup / Sideways)
    bb_width_ma50 = df['BB_Width'].rolling(50, min_periods=5).mean().replace(0, 1e-4)
    df['bb_squeeze_ratio'] = df['BB_Width'] / bb_width_ma50
    bb_width_pct = df['BB_Width'].rolling(100, min_periods=10).rank(pct=True).fillna(0.5)

    # BB Squeeze terkonfirmasi jika rasio sempit (< 0.85) atau persentil < 0.35
    df['is_bb_squeeze'] = np.where((df['bb_squeeze_ratio'] < 0.85) | (bb_width_pct < 0.35), 1, 0)

    # 3. BB Mengembang (Expansion)
    df['is_bb_expanding'] = np.where((df['BB_Width_Slope'] > 0) & (df['bb_squeeze_ratio'] > 1.05), 1, 0)

    # 4. Deteksi Running Momentum (CSM aktif dalam 15 candle terakhir)
    csm_buy_active = df['is_CSM_Buy'].rolling(15, min_periods=1).max().fillna(0)
    csm_sell_active = df['is_CSM_Sell'].rolling(15, min_periods=1).max().fillna(0)

    # 5. Deteksi Break Structure dari Squeeze (Transisi Squeeze -> Real Trend)
    # Pernah squeeze dalam 15 candle sebelumnya, lalu candle close menembus BB Upper/Lower dan BB mulai mengembang
    recent_squeeze = df['is_bb_squeeze'].shift(1).rolling(15, min_periods=1).max().fillna(0)
    df['is_breakout_bull'] = np.where(
        (recent_squeeze == 1) & (df['close'] > df['BB_Upper']) & (df['BB_Width_Slope'] > 0), 1, 0
    )
    df['is_breakout_bear'] = np.where(
        (recent_squeeze == 1) & (df['close'] < df['BB_Lower']) & (df['BB_Width_Slope'] > 0), 1, 0
    )

    brk_buy_recent = df['is_breakout_bull'].rolling(15, min_periods=1).max().fillna(0)
    brk_sell_recent = df['is_breakout_bear'].rolling(15, min_periods=1).max().fillna(0)

    # 6. Status Running Trend Sejati (Running Bullish & Running Bearish)
    # Bullish: BB mengembang ke atas, SMA 20 miring naik, harga di atas Mid BB, atau CSM Buy aktif, atau Breakout Bull
    df['is_running_bull'] = np.where(
        ((df['is_bb_expanding'] == 1) & (df['SMA_20_Slope'] > 0) & (df['close'] >= df['SMA_20'])) |
        (csm_buy_active == 1) | (brk_buy_recent == 1),
        1, 0
    )
    # Bearish: BB mengembang ke bawah, SMA 20 miring turun, harga di bawah Mid BB, atau CSM Sell aktif, atau Breakout Bear
    df['is_running_bear'] = np.where(
        ((df['is_bb_expanding'] == 1) & (df['SMA_20_Slope'] < 0) & (df['close'] <= df['SMA_20'])) |
        (csm_sell_active == 1) | (brk_sell_recent == 1),
        1, 0
    )

    # 7. Hukum Larangan Counter Trend (Anti Counter-Trend Shield)
    # Saat running bull atau breakout bull: HARAM SELL!
    df['forbid_sell'] = np.where((df['is_running_bull'] == 1) | (df['is_breakout_bull'] == 1), 1, 0)
    # Saat running bear atau breakout bear: HARAM BUY!
    df['forbid_buy'] = np.where((df['is_running_bear'] == 1) | (df['is_breakout_bear'] == 1), 1, 0)

    # 8. Filter Squeeze Extreme Only (Di fase squeeze, HANYA boleh buy di Lower BB & sell di Upper BB)
    atr_est = (df['BB_Width'] / 4.0).replace(0, 1e-4)
    squeeze_buffer = 0.20 * atr_est
    df['is_squeeze_buy_allowed'] = np.where(
        (df['is_bb_squeeze'] == 0) | (df['low'] <= (df['BB_Lower'] + squeeze_buffer)), 1, 0
    )
    df['is_squeeze_sell_allowed'] = np.where(
        (df['is_bb_squeeze'] == 0) | (df['high'] >= (df['BB_Upper'] - squeeze_buffer)), 1, 0
    )

    return df


def calculate_bbma_sequence_features(df: pd.DataFrame, lookback: int = 30) -> pd.DataFrame:
    df = df.copy()
    n = len(df)
    atr_safe = np.maximum(
        pd.to_numeric(df['ATR_14'], errors='coerce').fillna(0.001).values if 'ATR_14' in df.columns else np.full(n, 0.001),
        1e-5
    )

    # ----------------------------------------------------------------
    # 1. BARS SINCE LAST TRIGGER EVENT (CSA / CSAK / CSM)
    # Vectorized: forward-fill index last occurrence via np.maximum.accumulate
    # Hasil: float [1, lookback+1]. Makin kecil = makin fresh / relevan.
    # ----------------------------------------------------------------
    idx_arr = np.arange(n, dtype=np.float64)

    for col_flag, result_col in [
        ('is_CSA_Buy',     'bars_since_csa_buy'),
        ('is_CSA_Sell',    'bars_since_csa_sell'),
        ('is_CSAK_Buy',    'bars_since_csak_buy'),
        ('is_CSAK_Sell',   'bars_since_csak_sell'),
        ('is_CSM_Buy',     'bars_since_csm_buy'),
        ('is_CSM_Sell',    'bars_since_csm_sell'),
        ('is_Extrem_Buy',  'bars_since_extrem_buy'),
        ('is_Extrem_Sell', 'bars_since_extrem_sell'),
    ]:
        if col_flag not in df.columns:
            df[result_col] = float(lookback + 1)
            continue

        flags = pd.to_numeric(df[col_flag], errors='coerce').fillna(0.0).values.astype(float)
        # last_event_idx[i] = index terakhir di mana flags == 1, atau -1 jika belum pernah
        last_event_idx = np.where(flags == 1.0, idx_arr, -1.0)
        last_event_idx = np.maximum.accumulate(last_event_idx)
        # bars_since = selisih index saat ini dengan index terakhir event
        bars_since = np.where(last_event_idx >= 0, idx_arr - last_event_idx, float(lookback + 1))
        # Clamp ke [1, lookback+1]: bar yang sama dianggap belum ada event sebelumnya
        bars_since = np.where(bars_since == 0.0, float(lookback + 1), bars_since)
        bars_since = np.clip(bars_since, 1.0, float(lookback + 1))
        df[result_col] = bars_since

    # ----------------------------------------------------------------
    # 2. FRESHNESS SCORE (Exponential decay dari kekinian event)
    # Skor 1.0 = baru terjadi, mendekati 0 = sudah lama
    # Decay half-life = 5 candle
    # ----------------------------------------------------------------
    decay_k = np.log(2) / 5.0

    df['freshness_csa_buy']   = np.exp(-decay_k * np.minimum(df['bars_since_csa_buy'].values,   lookback))
    df['freshness_csa_sell']  = np.exp(-decay_k * np.minimum(df['bars_since_csa_sell'].values,  lookback))
    df['freshness_csak_buy']  = np.exp(-decay_k * np.minimum(df['bars_since_csak_buy'].values,  lookback))
    df['freshness_csak_sell'] = np.exp(-decay_k * np.minimum(df['bars_since_csak_sell'].values, lookback))
    df['freshness_csm_buy']   = np.exp(-decay_k * np.minimum(df['bars_since_csm_buy'].values,   lookback))
    df['freshness_csm_sell']  = np.exp(-decay_k * np.minimum(df['bars_since_csm_sell'].values,  lookback))

    # ----------------------------------------------------------------
    # 3. TRIGGER CANDLE MOMENTUM RATIO
    # Vectorized: fancy-indexing array origin_idx tanpa Python loop
    # ----------------------------------------------------------------
    close_s = pd.to_numeric(df['close'], errors='coerce').fillna(0.0)
    open_s  = pd.to_numeric(df['open'], errors='coerce').fillna(close_s)
    body_diff_s = (close_s - open_s).abs()
    body_sizes = (
        pd.to_numeric(df['body_size'], errors='coerce').fillna(body_diff_s).values
        if 'body_size' in df.columns
        else body_diff_s.values
    )

    for bars_col, result_col in [
        ('bars_since_csa_buy',   'trigger_momentum_csa_buy'),
        ('bars_since_csa_sell',  'trigger_momentum_csa_sell'),
        ('bars_since_csak_buy',  'trigger_momentum_csak_buy'),
        ('bars_since_csak_sell', 'trigger_momentum_csak_sell'),
        ('bars_since_csm_buy',   'trigger_momentum_csm_buy'),
        ('bars_since_csm_sell',  'trigger_momentum_csm_sell'),
    ]:
        bars_arr = df[bars_col].values.astype(np.float64)
        valid_mask = (bars_arr >= 1.0) & (bars_arr <= lookback)
        origin_idx = (idx_arr - bars_arr).astype(np.int64)
        origin_idx_safe = np.clip(origin_idx, 0, n - 1)
        momentum = body_sizes[origin_idx_safe] / atr_safe[origin_idx_safe]
        df[result_col] = np.where(valid_mask, momentum, 0.0)

    # ----------------------------------------------------------------
    # 4. KOMPOSIT TRIGGER SCORE PER ARAH
    # CSM > CSAK > CSA dalam hierarki kekuatan konfirmasi.
    # ----------------------------------------------------------------
    df['trigger_score_buy'] = np.maximum.reduce([
        df['freshness_csm_buy'].values   * df['trigger_momentum_csm_buy'].values   * 3.0,
        df['freshness_csak_buy'].values  * df['trigger_momentum_csak_buy'].values  * 2.0,
        df['freshness_csa_buy'].values   * df['trigger_momentum_csa_buy'].values   * 1.0,
    ])
    df['trigger_score_sell'] = np.maximum.reduce([
        df['freshness_csm_sell'].values  * df['trigger_momentum_csm_sell'].values  * 3.0,
        df['freshness_csak_sell'].values * df['trigger_momentum_csak_sell'].values * 2.0,
        df['freshness_csa_sell'].values  * df['trigger_momentum_csa_sell'].values  * 1.0,
    ])

    # ----------------------------------------------------------------
    # 5. DISTANCE TO OPPOSITE BB (Ruang gerak tersedia, dimensionless)
    # ----------------------------------------------------------------
    atr_safe_s = pd.Series(atr_safe, index=df.index)
    close_v = close_s.values
    if 'BB_Upper' in df.columns and 'BB_Lower' in df.columns:
        bb_u = pd.to_numeric(df['BB_Upper'], errors='coerce').fillna(close_s + atr_safe_s * 2.0).values
        bb_l = pd.to_numeric(df['BB_Lower'], errors='coerce').fillna(close_s - atr_safe_s * 2.0).values
        df['room_to_bb_upper'] = (bb_u - close_v) / atr_safe
        df['room_to_bb_lower'] = (close_v - bb_l) / atr_safe

    # ----------------------------------------------------------------
    # 6. MHV LIKELIHOOD SCORE
    # Pasar Hilang Volume: BB melebar tapi harga tidak bergerak dari Mid.
    # ----------------------------------------------------------------
    if 'BB_Width' in df.columns and 'SMA_20' in df.columns:
        bb_width_s   = pd.to_numeric(df['BB_Width'], errors='coerce').fillna(atr_safe_s * 4.0)
        bb_width     = bb_width_s.values
        bb_width_ma  = bb_width_s.rolling(20, min_periods=5).mean().fillna(float(np.mean(bb_width))).values
        sma20_v      = pd.to_numeric(df['SMA_20'], errors='coerce').fillna(close_s).values
        price_dist   = np.abs(close_v - sma20_v)
        bb_expansion = bb_width / np.maximum(bb_width_ma, 1e-5)
        price_compr  = 1.0 - np.clip(price_dist / np.maximum(bb_width * 0.5, 1e-5), 0.0, 1.0)
        df['mhv_likelihood'] = np.clip(bb_expansion * price_compr, 0.0, 3.0)

    # ----------------------------------------------------------------
    # 7. RE-ENTRY BODY REJECTION QUALITY (Slide 33)
    # Wick panjang ke zona MA + Body tidak tembus Mid BB ke arah berlawanan.
    # ----------------------------------------------------------------
    if all(c in df.columns for c in ['lower_wick', 'upper_wick', 'body_size', 'SMA_20']):
        lower_wick = pd.to_numeric(df['lower_wick'], errors='coerce').fillna(0.0).values
        upper_wick = pd.to_numeric(df['upper_wick'], errors='coerce').fillna(0.0).values
        sma20      = pd.to_numeric(df['SMA_20'], errors='coerce').fillna(close_s).values
        bb_upper   = pd.to_numeric(df['BB_Upper'], errors='coerce').fillna(close_s + atr_safe_s * 2.0).values if 'BB_Upper' in df.columns else (close_s + atr_safe_s * 2.0).values
        bb_lower   = pd.to_numeric(df['BB_Lower'], errors='coerce').fillna(close_s - atr_safe_s * 2.0).values if 'BB_Lower' in df.columns else (close_s - atr_safe_s * 2.0).values

        buy_wick_ratio = lower_wick / np.maximum(atr_safe, 1e-5)
        buy_body_ok    = ((close_v >= sma20) & (close_v <= bb_upper)).astype(float)
        df['reentry_quality_buy']  = np.clip(buy_wick_ratio * buy_body_ok, 0.0, 3.0)

        sell_wick_ratio = upper_wick / np.maximum(atr_safe, 1e-5)
        sell_body_ok    = ((close_v <= sma20) & (close_v >= bb_lower)).astype(float)
        df['reentry_quality_sell'] = np.clip(sell_wick_ratio * sell_body_ok, 0.0, 3.0)

    return df


# ---------------------------------------------------------------------------
# FRACTAL ORIGIN DETECTION
# Mendeteksi di timeframe mana (H1, M15, M5) setup Re-entry sedang terjadi
# secara simultan. Semakin besar TF Re-entry yang aktif, semakin besar
# kapasitas ekspansi yang dimiliki setup tersebut.
# ---------------------------------------------------------------------------

def calculate_fractal_origin(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mendeteksi level fraktal asal dari setup Re-entry berdasarkan data
    multi-timeframe yang sudah di-merge (suffix _setup, _trend, _m5, _m15).

    Menghasilkan:
    - is_reentry_buy/sell_base  : Re-entry valid di TF base (M5)
    - is_reentry_buy/sell_setup : Re-entry valid di TF setup (M15)
    - is_reentry_buy/sell_trend : Re-entry valid di TF trend (H1/H4)
    - fractal_origin_buy/sell   : Skor 0..3 (jumlah TF yang simultan aktif)
    - fractal_capacity_buy/sell : Estimasi kapasitas R ekspansi (kontinu)
    - atr_ratio_setup_base      : Rasio volatilitas TF setup vs base
    - atr_ratio_trend_base      : Rasio volatilitas TF trend vs base
    """
    df = df.copy()
    n  = len(df)

    def _reentry_touch(low_arr, high_arr, atr_arr,
                       lw5l, lw10l, lw5h, lw10h, buf_ratio=0.35):
        """Cek apakah harga sedang di zona Re-entry LWMA (buy & sell)."""
        lwma_low_zone  = np.maximum(lw5l, lw10l)
        lwma_high_zone = np.minimum(lw5h, lw10h)
        buf = buf_ratio * np.maximum(atr_arr, 1e-5)
        return (
            (low_arr  <= lwma_low_zone  + buf).astype(float),
            (high_arr >= lwma_high_zone - buf).astype(float)
        )

    def _col(base, sfx, fallback):
        col = f"{base}{sfx}"
        if col in df.columns:
            return pd.to_numeric(df[col], errors='coerce').fillna(float(fallback)).values.astype(float)
        return np.full(n, float(fallback))

    low_b  = pd.to_numeric(df['low'], errors='coerce').fillna(0.0).values  if 'low'  in df.columns else np.zeros(n)
    high_b = pd.to_numeric(df['high'], errors='coerce').fillna(0.0).values if 'high' in df.columns else np.zeros(n)

    # ---- BASE TF ----
    atr_b  = np.maximum(_col('ATR_14', '', 0.001), 1e-5)
    lw5l_b = _col('LWMA_5_Low',  '', 0.0); lw10l_b = _col('LWMA_10_Low',  '', 0.0)
    lw5h_b = _col('LWMA_5_High', '', 0.0); lw10h_b = _col('LWMA_10_High', '', 0.0)
    buy_b, sell_b = _reentry_touch(low_b, high_b, atr_b, lw5l_b, lw10l_b, lw5h_b, lw10h_b, 0.35)

    # ---- SETUP TF ----
    s = '_setup' if 'LWMA_5_Low_setup' in df.columns else '_m15'
    atr_s  = np.maximum(_col('ATR_14', s, 0.001), 1e-5)
    lw5l_s = _col('LWMA_5_Low',  s, lw5l_b.mean()); lw10l_s = _col('LWMA_10_Low',  s, lw10l_b.mean())
    lw5h_s = _col('LWMA_5_High', s, lw5h_b.mean()); lw10h_s = _col('LWMA_10_High', s, lw10h_b.mean())
    buy_s, sell_s = _reentry_touch(low_b, high_b, atr_s, lw5l_s, lw10l_s, lw5h_s, lw10h_s, 0.40)

    # ---- TREND TF ----
    t = '_trend' if 'LWMA_5_Low_trend' in df.columns else '_h1'
    atr_t  = np.maximum(_col('ATR_14', t, 0.001), 1e-5)
    lw5l_t = _col('LWMA_5_Low',  t, lw5l_b.mean()); lw10l_t = _col('LWMA_10_Low',  t, lw10l_b.mean())
    lw5h_t = _col('LWMA_5_High', t, lw5h_b.mean()); lw10h_t = _col('LWMA_10_High', t, lw10h_b.mean())
    buy_t, sell_t = _reentry_touch(low_b, high_b, atr_t, lw5l_t, lw10l_t, lw5h_t, lw10h_t, 0.50)

    # ---- Simpan semua hasil ----
    df['is_reentry_buy_base']   = buy_b;  df['is_reentry_sell_base']  = sell_b
    df['is_reentry_buy_setup']  = buy_s;  df['is_reentry_sell_setup'] = sell_s
    df['is_reentry_buy_trend']  = buy_t;  df['is_reentry_sell_trend'] = sell_t

    df['fractal_origin_buy']  = buy_b  + buy_s  + buy_t
    df['fractal_origin_sell'] = sell_b + sell_s + sell_t

    df['fractal_capacity_buy']  = 1.0 + buy_s  * 1.5 + buy_t  * 2.5
    df['fractal_capacity_sell'] = 1.0 + sell_s * 1.5 + sell_t * 2.5

    df['atr_ratio_setup_base'] = atr_s / np.maximum(atr_b, 1e-5)
    df['atr_ratio_trend_base'] = atr_t / np.maximum(atr_b, 1e-5)

    return df
