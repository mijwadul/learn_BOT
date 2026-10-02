import logging
import numpy as np
import pandas as pd
from utils.indicators import calculate_atr

logger = logging.getLogger(__name__)


def generate_targets(
    df: pd.DataFrame,
    tp_mult: float = 1.5,
    sl_mult: float = 1.0,
    horizon: int = 36,
    symbol: str = None,
    spread_pips: float = 0.0,
    **kwargs
) -> pd.DataFrame:
    """
    Pelabelan Target 'Beri Saya Profit' (Pure Forward Realized Profit / Triple Barrier).
    Bebas dari segala aturan manual. Model diberikan kebebasan penuh menemukan
    probabilitas profitnya sendiri pada setiap bar harga.

    Target yang dihasilkan:
    - Target_Class   : 0 = Neutral/Loss/Chop, 1 = BUY Profit, 2 = SELL Profit
    - Target_Buy     : 1 jika BUY mencapai TP sebelum SL (dikurangi spread), 0 sebaliknya
    - Target_Sell    : 1 jika SELL mencapai TP sebelum SL (dikurangi spread), 0 sebaliknya
    - Target_Normal  : Alias untuk Target_Buy (kompatibilitas mundur)
    - Target_Runner  : Alias untuk Target_Sell (kompatibilitas mundur)
    - forward_mfe_r  : Rasio keuntungan maksimum yang dicapai dalam horizon
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    n = len(df)

    if 'ATR_14' in df.columns and not df['ATR_14'].isna().all():
        atr_series = df['ATR_14']
    elif 'atr_14' in df.columns and not df['atr_14'].isna().all():
        atr_series = df['atr_14']
    else:
        atr_series = calculate_atr(df, 14)
    df['ATR_14'] = atr_series
    df['atr_14'] = atr_series
    atrs = np.maximum(pd.to_numeric(atr_series, errors='coerce').fillna(0.01).values, 1e-4)

    close_series = pd.to_numeric(df['close'], errors='coerce').fillna(0.0)
    high_series = pd.to_numeric(df['high'], errors='coerce').fillna(close_series)
    low_series = pd.to_numeric(df['low'], errors='coerce').fillna(close_series)

    closes = close_series.values
    highs = high_series.values
    lows = low_series.values

    labels_class = np.zeros(n, dtype=np.int8)
    labels_buy = np.zeros(n, dtype=np.int8)
    labels_sell = np.zeros(n, dtype=np.int8)
    mfe_arr = np.zeros(n, dtype=np.float32)

    sym = str(symbol or getattr(df, 'attrs', {}).get('symbol') or 'XAUUSD').upper()
    if 'BTC' in sym:
        point_multiplier = 1.0
        default_cost = 5.0
    elif 'XAU' in sym or 'GOLD' in sym:
        point_multiplier = 0.01
        default_cost = 0.25
    elif 'OIL' in sym or 'USO' in sym:
        point_multiplier = 0.001
        default_cost = 0.04
    elif 'JPY' in sym:
        point_multiplier = 0.001
        default_cost = 0.02
    else:
        point_multiplier = 0.00001
        default_cost = 0.00015

    if spread_pips > 0:
        default_cost = spread_pips * (0.01 if 'JPY' in sym else (0.1 if ('XAU' in sym or 'GOLD' in sym) else (1.0 if 'BTC' in sym else 0.0001)))

    has_real_spread = ('spread' in df.columns) and not df['spread'].isna().all()
    if has_real_spread:
        spread_series = pd.to_numeric(df['spread'], errors='coerce').fillna(default_cost / point_multiplier)
        spread_arr = np.maximum(spread_series.values * point_multiplier, 0.5 * default_cost)
    else:
        spread_arr = np.full(n, default_cost, dtype=np.float32)

    for i in range(n):
        c_0 = closes[i]
        atr_i = atrs[i]
        tp_dist = tp_mult * atr_i
        sl_dist = sl_mult * atr_i
        spread_cost = float(spread_arr[i])

        # Realistis MT5 Execution:
        # BUY: Entry di Ask (c_0 + spread). TP tercapai jika High >= c_0 + spread + tp_dist. SL kena jika Low <= c_0 + spread - sl_dist.
        buy_tp_price = c_0 + spread_cost + tp_dist
        buy_sl_price = c_0 + spread_cost - sl_dist

        # SELL: Entry di Bid (c_0). TP tercapai jika Ask <= c_0 - tp_dist => Low <= c_0 - tp_dist - spread_cost.
        #       SL kena jika Ask >= c_0 + sl_dist => High >= c_0 + sl_dist - spread_cost.
        sell_tp_price = c_0 - tp_dist - spread_cost
        sell_sl_price = c_0 + sl_dist - spread_cost

        buy_hit_tp = False
        buy_hit_sl = False
        sell_hit_tp = False
        sell_hit_sl = False

        max_fav_excursion = 0.0

        for j in range(i + 1, min(i + horizon + 1, n)):
            h_j = highs[j]
            l_j = lows[j]

            # Evaluasi BUY (pessimistic: jika candle menyentuh SL dan TP di bar yang sama, anggap SL dulu)
            if not buy_hit_sl and not buy_hit_tp:
                if l_j <= buy_sl_price:
                    buy_hit_sl = True
                elif h_j >= buy_tp_price:
                    buy_hit_tp = True

            # Evaluasi SELL (pessimistic: jika candle menyentuh SL dan TP di bar yang sama, anggap SL dulu)
            if not sell_hit_sl and not sell_hit_tp:
                if h_j >= sell_sl_price:
                    sell_hit_sl = True
                elif l_j <= sell_tp_price:
                    sell_hit_tp = True

            # MFE (Maximum Favorable Excursion) untuk keperluan diagnosa riset internal
            fav_move = max(h_j - c_0, c_0 - l_j)
            if fav_move > max_fav_excursion:
                max_fav_excursion = fav_move

            if (buy_hit_tp or buy_hit_sl) and (sell_hit_tp or sell_hit_sl):
                break

        mfe_arr[i] = max_fav_excursion / atr_i

        # Menghindari bias asimetris: jika dua-duanya hit TP tanpa SL (chop/whipsaw), klasifikasikan sebagai 0 (Chop)
        if buy_hit_tp and not buy_hit_sl and not (sell_hit_tp and not sell_hit_sl):
            labels_buy[i] = 1
            labels_class[i] = 1
        elif sell_hit_tp and not sell_hit_sl and not (buy_hit_tp and not buy_hit_sl):
            labels_sell[i] = 1
            labels_class[i] = 2

    df['Target_Class'] = labels_class
    df['Target_Buy'] = labels_buy
    df['Target_Sell'] = labels_sell
    df['_forward_mfe_r'] = mfe_arr
    df['forward_mfe_r'] = mfe_arr

    # Kompatibilitas mundur
    df['Target_Normal'] = labels_buy
    df['Target_Runner'] = labels_sell
    df['setup_dir'] = labels_class

    return df


def compute_sample_uniqueness(n_samples: int, horizon: int = 36) -> np.ndarray:
    """
    Menghitung bobot keunikan sampel (Sample Uniqueness) Marcos Lopez de Prado (AFML Bab 4).
    Mereduksi multikolinearitas temporal akibat jendela forward Triple Barrier yang saling tumpang tindih.
    """
    if n_samples <= 0:
        return np.array([], dtype=np.float32)
    horizon = max(1, int(horizon))
    idx = np.arange(n_samples)
    concurrency = np.minimum(idx + 1, np.minimum(horizon, n_samples - idx)).astype(np.float32)
    concurrency = np.maximum(concurrency, 1.0)
    inv_c = 1.0 / concurrency

    kernel = np.ones(horizon, dtype=np.float32) / float(horizon)
    uniqueness = np.convolve(inv_c, kernel, mode='full')[:n_samples]
    return (uniqueness / max(1e-4, float(np.mean(uniqueness)))).astype(np.float32)

