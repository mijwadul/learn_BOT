import logging
import MetaTrader5 as mt5
import numpy as np
import pandas as pd
import lightgbm as lgb
from typing import Dict, Any, List

from utils.mt5_utils import get_rates, resolve_broker_symbol
from utils.indicators import calculate_bbma
from .feature_engineer import add_normalized_features, extract_and_lock_features
from .target_labeler import generate_targets

logger = logging.getLogger("TimeframeDiscovery")

import re
from typing import Dict, Any, List, Optional

from utils.mt5_utils import get_rates, resolve_broker_symbol
from utils.indicators import calculate_bbma
from .feature_engineer import add_normalized_features, extract_and_lock_features
from .target_labeler import generate_targets

logger = logging.getLogger("TimeframeDiscovery")

def get_mt5_timeframe_constant(tf_str: str) -> Optional[int]:
    """
    Mengembalikan konstanta bawaan MetaTrader 5 jika didukung secara native.
    MT5 mendukung: M1..M6, M10, M12, M15, M20, M30, H1..H4, H6, H8, H12, D1.
    """
    clean_tf = str(tf_str or "M15").strip().upper()
    native_map = {
        "M1": getattr(mt5, "TIMEFRAME_M1", 1),
        "M2": getattr(mt5, "TIMEFRAME_M2", 2),
        "M3": getattr(mt5, "TIMEFRAME_M3", 3),
        "M4": getattr(mt5, "TIMEFRAME_M4", 4),
        "M5": getattr(mt5, "TIMEFRAME_M5", 5),
        "M6": getattr(mt5, "TIMEFRAME_M6", 6),
        "M10": getattr(mt5, "TIMEFRAME_M10", 10),
        "M12": getattr(mt5, "TIMEFRAME_M12", 12),
        "M15": getattr(mt5, "TIMEFRAME_M15", 15),
        "M20": getattr(mt5, "TIMEFRAME_M20", 20),
        "M30": getattr(mt5, "TIMEFRAME_M30", 30),
        "H1": getattr(mt5, "TIMEFRAME_H1", 16385),
        "H2": getattr(mt5, "TIMEFRAME_H2", 16386),
        "H3": getattr(mt5, "TIMEFRAME_H3", 16387),
        "H4": getattr(mt5, "TIMEFRAME_H4", 16388),
        "H6": getattr(mt5, "TIMEFRAME_H6", 16390),
        "H8": getattr(mt5, "TIMEFRAME_H8", 16392),
        "H12": getattr(mt5, "TIMEFRAME_H12", 16396),
        "D1": getattr(mt5, "TIMEFRAME_D1", 16408),
    }
    return native_map.get(clean_tf)


def tf_to_pandas_rule(tf_str: str) -> str:
    """
    Mengonversi string timeframe bebas (M1, M7, M35, H2, dll.) ke aturan string Pandas resample.
    Contoh: 'M7' -> '7min', 'M35' -> '35min', 'H2' -> '2h', 'D1' -> '1D'.
    """
    clean_tf = str(tf_str or "M15").strip().upper()
    m_min = re.match(r"^M(\d+)$", clean_tf)
    if m_min:
        return f"{m_min.group(1)}min"
    m_hour = re.match(r"^H(\d+)$", clean_tf)
    if m_hour:
        return f"{m_hour.group(1)}h"
    m_day = re.match(r"^D(\d*)$", clean_tf)
    if m_day:
        d_val = m_day.group(1) or "1"
        return f"{d_val}D"
    return "15min"


def resample_m1_df(df_m1: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """
    Resample DataFrame M1 atomik ke timeframe target dengan origin='start_day'
    agar batas candle harian konsisten deterministik.
    """
    rule = tf_to_pandas_rule(target_tf)
    if rule in ("1min", "1m"):
        return df_m1.copy()
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    if 'tick_volume' in df_m1.columns:
        agg['tick_volume'] = 'sum'
    if 'spread' in df_m1.columns:
        agg['spread'] = 'mean'
    for c in df_m1.columns:
        if c not in agg and c not in ('time', 'timestamp', 'datetime', 'id'):
            if pd.api.types.is_numeric_dtype(df_m1[c]):
                agg[c] = 'last'
    res = df_m1.resample(rule, origin='start_day').agg(agg).dropna(subset=['open', 'close'])
    return res


def discover_best_timeframe(
    symbol: str = "XAUUSD",
    candidate_tfs: List[str] = None,
    n_candles: int = 5000
) -> Dict[str, Any]:
    if candidate_tfs is None:
        # Kandidat strategis mencakup timeframe non-standar & native (M5, M7, M15, M35, H1, H2)
        candidate_tfs = ["M5", "M7", "M15", "M35", "H1", "H2"]

    clean_sym = str(symbol or "XAUUSD").upper()
    broker_sym = resolve_broker_symbol(clean_sym)
    mt5.symbol_select(broker_sym, True)

    results = {}
    best_tf = "M5"
    best_score = -999.0

    df_local_m1 = None
    try:
        from database import sync_engine
        from sqlalchemy import text
        import re
        clean_tbl = re.sub(r'[^a-zA-Z0-9]', '', clean_sym.lower())
        for m1_tbl in [f"raw_market_m1_{clean_tbl}", f"market_data_m1_{clean_tbl}", f"market_data_{clean_tbl}"]:
            check_q = f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{m1_tbl}')"
            with sync_engine.connect() as conn:
                exists = conn.execute(text(check_q)).scalar()
            if exists:
                q = f'SELECT * FROM (SELECT * FROM "{m1_tbl}" ORDER BY time DESC LIMIT 60000) sub ORDER BY time ASC'
                chunks = []
                for chk in pd.read_sql(q, con=sync_engine, chunksize=20000):
                    if 'time' in chk.columns:
                        chk['time'] = pd.to_datetime(chk['time'])
                    chunks.append(chk)
                if chunks:
                    df_local_m1 = pd.concat(chunks, ignore_index=True)
                    df_local_m1.set_index('time', inplace=True)
                    logger.info(f"⚡ [TIMEFRAME DISCOVERY - M1 DB] Menggunakan {len(df_local_m1):,} candle M1 lokal ({m1_tbl}).")
                break
    except Exception as e_m1:
        logger.debug(f"Pencarian M1 lokal dilewati: {e_m1}")

    logger.info(f"🔎 [TIMEFRAME DISCOVERY] Memulai pencarian timeframe paling akurat untuk {clean_sym}...")

    for tf_str in candidate_tfs:
        try:
            logger.info(f"[{clean_sym}] Menguji kandidat timeframe: {tf_str}...")
            rates_df = None
            if df_local_m1 is not None and len(df_local_m1) >= 2000:
                rates_df = resample_m1_df(df_local_m1, tf_str)
            else:
                tf_const = get_mt5_timeframe_constant(tf_str)
                if tf_const is not None:
                    rates_df = get_rates(broker_sym, tf_const, n_candles + 100, start_pos=0)
                    if rates_df is not None and not rates_df.empty:
                        rates_df.set_index('time', inplace=True)
                else:
                    # Synthetic M1 fallback dari MT5 jika timeframe non-standar (misal M7, M35)
                    m_min = re.match(r"^M(\d+)$", tf_str.upper())
                    mins = int(m_min.group(1)) if m_min else 15
                    m1_needed = min((n_candles + 100) * mins, 60000)
                    raw_m1 = get_rates(broker_sym, mt5.TIMEFRAME_M1, m1_needed, start_pos=0)
                    if raw_m1 is not None and not raw_m1.empty:
                        raw_m1.set_index('time', inplace=True)
                        rates_df = resample_m1_df(raw_m1, tf_str)

            if rates_df is None or len(rates_df) < 500:
                logger.warning(f"[{clean_sym}-{tf_str}] Data tidak cukup untuk evaluasi.")
                continue
            rates_df = calculate_bbma(rates_df)
            rates_df = add_normalized_features(rates_df)
            rates_df = generate_targets(rates_df, tp_mult=1.5, sl_mult=1.0, horizon=36, symbol=clean_sym)

            feats = extract_and_lock_features(rates_df)
            if not feats:
                continue

            X = rates_df[feats].copy()
            y = rates_df['Target_Class'].copy()

            # Pastikan numerik
            for col in feats:
                X[col] = pd.to_numeric(X[col], errors='coerce').fillna(0.0)

            # Split Train 75% - Test 25% dengan Purged Embargo (Marcos Lopez de Prado)
            # Menghapus horizon (36 bar) terakhir dari X_train agar label train tidak melihat ke dalam X_test
            horizon = 36
            split_idx = int(len(X) * 0.75)
            train_end_idx = max(50, split_idx - horizon)
            X_train, y_train = X.iloc[:train_end_idx], y.iloc[:train_end_idx]
            X_test, y_test = X.iloc[split_idx:], y.iloc[split_idx:]

            if len(np.unique(y_train)) < 2:
                continue

            clf = lgb.LGBMClassifier(
                n_estimators=100,
                learning_rate=0.05,
                max_depth=4,
                num_leaves=15,
                objective='multiclass',
                num_class=3,
                random_state=42,
                verbose=-1
            )
            clf.fit(X_train, y_train)

            # Evaluasi pada data Test (OOS)
            probs = clf.predict_proba(X_test)
            classes = list(getattr(clf, 'classes_', [0, 1, 2]))
            idx_buy = classes.index(1) if 1 in classes else -1
            idx_sell = classes.index(2) if 2 in classes else -1

            p_buy = probs[:, idx_buy] if idx_buy >= 0 else np.zeros(len(X_test))
            p_sell = probs[:, idx_sell] if idx_sell >= 0 else np.zeros(len(X_test))

            # Simulasi trade sinyal realistis dengan cooldown posisi (Position State Simulation)
            threshold = 0.45
            buy_signals = (p_buy >= threshold) & (p_buy > p_sell)
            sell_signals = (p_sell >= threshold) & (p_sell > p_buy)

            wins = 0
            losses = 0
            gross_profit = 0.0
            gross_loss = 0.0

            y_test_vals = y_test.values
            cooldown_bars = 4
            cooldown_counter = 0

            for idx in range(len(y_test_vals)):
                if cooldown_counter > 0:
                    cooldown_counter -= 1
                    continue

                actual = y_test_vals[idx]
                if buy_signals[idx]:
                    if actual == 1:
                        wins += 1
                        gross_profit += 1.5
                    elif actual == 0 or actual == 2:
                        losses += 1
                        gross_loss += 1.0
                    cooldown_counter = cooldown_bars
                elif sell_signals[idx]:
                    if actual == 2:
                        wins += 1
                        gross_profit += 1.5
                    elif actual == 0 or actual == 1:
                        losses += 1
                        gross_loss += 1.0
                    cooldown_counter = cooldown_bars

            total_trades = wins + losses
            win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
            profit_factor = (gross_profit / max(1e-4, gross_loss)) if total_trades > 0 else 0.0
            expectancy = ((gross_profit - gross_loss) / total_trades) if total_trades > 0 else 0.0

            results[tf_str] = {
                "timeframe": tf_str,
                "total_trades": total_trades,
                "win_rate": round(win_rate, 2),
                "profit_factor": round(profit_factor, 2),
                "expectancy": round(expectancy, 3),
            }

            # Skor gabungan: Profit Factor + Expectancy + log(trades)
            composite_score = profit_factor * 1.5 + expectancy * 2.0 + (np.log1p(total_trades) * 0.2)
            if total_trades >= 15 and composite_score > best_score:
                best_score = composite_score
                best_tf = tf_str

            logger.info(f"[{clean_sym}-{tf_str}] Hasil: {total_trades} trades | WinRate: {win_rate:.1f}% | ProfitFactor: {profit_factor:.2f}")

        except Exception as e:
            logger.warning(f"Gagal mengevaluasi timeframe {tf_str} untuk {clean_sym}: {e}")

    logger.info(f"🏆 [TIMEFRAME DISCOVERY WINNER] {clean_sym} memilih timeframe optimal: {best_tf}")
    return {
        "symbol": clean_sym,
        "best_timeframe": best_tf,
        "results": results
    }
