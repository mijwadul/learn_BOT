import datetime
import logging
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger("OOSEvaluator")

# Threshold Kelulusan Minimum Institusional
FIT_PROPER_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "normal": {
        "min_win_rate": 52.0,      # Win Rate minimal 52% (pada RR 1:1.5)
        "min_profit_factor": 1.30, # Profit Factor minimal 1.3
        "min_sharpe_ratio": 0.80,  # Sharpe Ratio minimal 0.8
        "max_drawdown": 20.0,      # Max Drawdown maksimal 20%
        "min_trades": 30           # Signifikansi statistik minimal 30 transaksi
    },
    "runner": {
        "min_win_rate": 28.0,      # Win Rate minimal 28% (pada RR 1:5.0)
        "min_profit_factor": 1.20, # Profit Factor minimal 1.2
        "min_sharpe_ratio": 0.50,  # Sharpe Ratio minimal 0.5
        "max_drawdown": 35.0,      # Max Drawdown maksimal 35%
        "min_trades": 20           # Signifikansi statistik minimal 20 transaksi
    }
}

def evaluate_metrics(metrics: Dict[str, Any], criteria: Dict[str, Any]) -> tuple[bool, Dict[str, bool], list[str]]:
    """Evaluasi metrik portofolio finansial terhadap standar kelulusan."""
    wr = float(metrics.get("win_rate_pct", 0.0))
    pf = float(metrics.get("profit_factor", 0.0))
    sharpe = float(metrics.get("sharpe_ratio", 0.0))
    max_dd = float(metrics.get("max_drawdown_pct", 0.0))
    trades = int(metrics.get("total_trades", 0))

    min_wr = float(criteria.get("min_win_rate", 50.0))
    min_pf = float(criteria.get("min_profit_factor", 1.2))
    min_sharpe = float(criteria.get("min_sharpe_ratio", 0.5))
    max_dd_crit = float(criteria.get("max_drawdown", 25.0))
    min_trades = int(criteria.get("min_trades", 20))

    wr_pass = wr >= min_wr
    pf_pass = pf >= min_pf or np.isinf(pf)
    sharpe_pass = sharpe >= min_sharpe
    dd_pass = max_dd <= max_dd_crit
    trades_pass = trades >= min_trades

    checks = {
        "win_rate_passed": bool(wr_pass),
        "profit_factor_passed": bool(pf_pass),
        "sharpe_ratio_passed": bool(sharpe_pass),
        "drawdown_passed": bool(dd_pass),
        "trades_passed": bool(trades_pass)
    }

    reasons = []
    if not trades_pass:
        reasons.append(f"Total trades ({trades}) kurang dari ambang signifikansi statistik ({min_trades})")
    if not wr_pass:
        reasons.append(f"Win Rate ({wr:.1f}%) di bawah kriteria minimum ({min_wr:.1f}%)")
    if not pf_pass:
        reasons.append(f"Profit Factor ({pf:.2f}) di bawah kriteria minimum ({min_pf:.2f})")
    if not sharpe_pass:
        reasons.append(f"Sharpe Ratio ({sharpe:.2f}) di bawah kriteria minimum ({min_sharpe:.2f})")
    if not dd_pass:
        reasons.append(f"Max Drawdown ({max_dd:.1f}%) melebihi toleransi risiko ({max_dd_crit:.1f}%)")

    passed = bool(wr_pass and pf_pass and sharpe_pass and dd_pass and trades_pass)
    return passed, checks, reasons

def run_fit_proper_test(
    model: Any,
    researcher: Any,
    df_oos: pd.DataFrame,
    mode: str = "normal",
    symbol: str = "XAUUSD",
    custom_thresholds: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Menjalankan simulasi finansial VectorBT pada data Out-Of-Sample (OOS).
    Digunakan sebagai gerbang kualitas (Fit & Proper Test) sebelum model disimpan/di-deploy.
    """
    mode_str = str(mode).strip().lower()
    sym_clean = str(symbol).strip().upper()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Ambil kriteria kelulusan berbasis Quantitative Profile instrumen
    from .profiles import get_profile
    profile = get_profile(sym_clean)
    base_criteria = profile.get_criteria(mode_str)
    if custom_thresholds:
        base_criteria.update(custom_thresholds)

    # Validasi awal input data
    if df_oos is None or df_oos.empty or len(df_oos) < 30:
        logger.warning(f"[{sym_clean}] Data OOS kosong atau terlalu sedikit ({0 if df_oos is None else len(df_oos)} baris).")
        return {
            "symbol": sym_clean,
            "mode": mode_str,
            "evaluated_at": now_str,
            "passed": False,
            "threshold_used": 0.0,
            "metrics": {
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "total_trades": 0,
                "total_return_pct": 0.0
            },
            "criteria": base_criteria,
            "checks": {k: False for k in ["win_rate_passed", "profit_factor_passed", "sharpe_ratio_passed", "drawdown_passed", "trades_passed"]},
            "reasons": ["Dataset OOS kosong atau kurang dari 30 candle"]
        }

    try:
        # Urutkan kronologis
        df_calc = df_oos.copy()
        if 'time' in df_calc.columns:
            df_calc['time'] = pd.to_datetime(df_calc['time'])
            df_calc = df_calc.sort_values('time').set_index('time')
        elif not isinstance(df_calc.index, pd.DatetimeIndex):
            try:
                df_calc.index = pd.to_datetime(df_calc.index)
                df_calc = df_calc.sort_index()
            except Exception:
                pass

        # 1. Generate Indikator, Target, dan Fitur Normalisasi
        regime_cols = ('BB_Upper', 'forbid_buy', 'is_CSA_Buy', 'is_breakout_bull', 'is_running_bull', 'is_bb_squeeze', 'is_bb_expanding')
        if any(c not in df_calc.columns or (c in df_calc.columns and df_calc[c].isna().all()) for c in regime_cols):
            from utils.indicators import calculate_bbma
            df_calc = calculate_bbma(df_calc)

        from utils.indicators import calculate_atr
        if 'ATR_14' not in df_calc.columns or df_calc['ATR_14'].isna().all():
            df_calc['ATR_14'] = calculate_atr(df_calc, 14)
        if 'atr_14' not in df_calc.columns or df_calc['atr_14'].isna().all():
            df_calc['atr_14'] = df_calc['ATR_14']

        if hasattr(researcher, "generate_targets"):
            df_calc = researcher.generate_targets(df_calc, symbol=sym_clean)
        if hasattr(researcher, "add_normalized_features"):
            df_calc = researcher.add_normalized_features(df_calc)

        # 2. Pastikan fitur lengkap sesuai ekspektasi model LightGBM
        model_features = []
        if hasattr(model, 'feature_name_') and model.feature_name_ is not None:
            model_features = list(model.feature_name_)
        elif hasattr(model, 'booster_') and hasattr(model.booster_, 'feature_name'):
            model_features = list(model.booster_.feature_name())
        elif hasattr(researcher, 'get_model_features'):
            model_features = researcher.get_model_features(model, mode=mode_str)
        elif hasattr(researcher, 'features') and researcher.features:
            model_features = list(researcher.features)

        if not model_features:
            excluded = {'open', 'high', 'low', 'close', 'tick_volume', 'Target_Normal', 'Target_Runner', 'setup_dir', 'symbol', 'max_mfe_r', 'forward_mfe_r', 'fractal_horizon'}
            model_features = [c for c in df_calc.columns if c not in excluded and not any(kw in c.lower() for kw in ['target', 'mfe', 'forward', 'future', 'pnl', 'profit', 'horizon'])]

        X_oos = df_calc.reindex(columns=model_features, fill_value=0.0).copy()
        for col in model_features:
            if not (pd.api.types.is_numeric_dtype(X_oos[col]) or pd.api.types.is_bool_dtype(X_oos[col])):
                X_oos[col] = pd.to_numeric(X_oos[col], errors='coerce').fillna(0.0)

        # 3. Prediksi Probabilitas Kemenangan (Multiclass 3-Class & Binary Compatible)
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X_oos)
            classes = list(getattr(model, 'classes_', [0, 1, 2]))
            if len(classes) == 3:
                idx_buy = classes.index(1) if 1 in classes else -1
                idx_sell = classes.index(2) if 2 in classes else -1
                p_buy = probs[:, idx_buy] if idx_buy >= 0 else np.zeros(len(X_oos))
                p_sell = probs[:, idx_sell] if idx_sell >= 0 else np.zeros(len(X_oos))
                p_win = np.maximum(p_buy, p_sell)
            else:
                idx_w = classes.index(1) if 1 in classes else (1 if probs.shape[1] > 1 else 0)
                p_win = probs[:, idx_w] if probs.shape[1] > idx_w else probs[:, -1]
                p_buy = p_win
                p_sell = p_win
        elif hasattr(model, "predict"):
            p_win = model.predict(X_oos)
            p_buy = p_win
            p_sell = p_win
        else:
            raise ValueError("Model tidak memiliki method predict atau predict_proba")

        # 4. Filter Spasial Zona Re-entry BBMA LWMA
        low_s = pd.to_numeric(df_calc['low'], errors='coerce').fillna(0.0)
        high_s = pd.to_numeric(df_calc['high'], errors='coerce').fillna(0.0)
        lw5l = pd.to_numeric(df_calc.get('LWMA_5_Low', df_calc.get('lwma_5_low', low_s)), errors='coerce').fillna(low_s).values
        lw10l = pd.to_numeric(df_calc.get('LWMA_10_Low', df_calc.get('lwma_10_low', low_s)), errors='coerce').fillna(low_s).values
        lw5h = pd.to_numeric(df_calc.get('LWMA_5_High', df_calc.get('lwma_5_high', high_s)), errors='coerce').fillna(high_s).values
        lw10h = pd.to_numeric(df_calc.get('LWMA_10_High', df_calc.get('lwma_10_high', high_s)), errors='coerce').fillna(high_s).values

        lwma_low_zone = np.maximum(lw5l, lw10l)
        lwma_high_zone = np.minimum(lw5h, lw10h)
        if 'ATR_14' in df_calc.columns and not df_calc['ATR_14'].isna().all():
            atr_s = df_calc['ATR_14']
        elif 'atr_14' in df_calc.columns and not df_calc['atr_14'].isna().all():
            atr_s = df_calc['atr_14']
        else:
            from utils.indicators import calculate_atr
            atr_s = calculate_atr(df_calc, 14)
        atrs = np.maximum(pd.to_numeric(atr_s, errors='coerce').fillna(0.001).values, 1e-4)
        buffer = profile.zone_buffer_ratio * atrs

        low_oos = low_s.values
        high_oos = high_s.values
        is_valid_buy = (low_oos <= (lwma_low_zone + buffer))
        is_valid_sell = (high_oos >= (lwma_high_zone - buffer))

        # Filter Zon Zero Loss (ZZL) Wajib jika dimandatkan oleh profile aset (misal XAUUSD)
        if profile.mandate_zzl:
            close_s = pd.to_numeric(df_calc['close'], errors='coerce').fillna(0.0)
            close_oos = close_s.values
            ema_val = pd.to_numeric(df_calc.get('EMA_50', df_calc.get('ema_50', close_s)), errors='coerce').fillna(close_s).values
            sma_val = pd.to_numeric(df_calc.get('SMA_20', df_calc.get('sma_20', close_s)), errors='coerce').fillna(close_s).values
            is_valid_buy = is_valid_buy & (close_oos >= ema_val) & (sma_val >= ema_val)
            is_valid_sell = is_valid_sell & (close_oos <= ema_val) & (sma_val <= ema_val)

        # 4b. Filter Trigger BBMA — Sinkronisasi dengan target_labeler
        # target_labeler HANYA memberi label positif jika ada CSA/CSAK/CSM dalam 30 bar
        # sebelum candle entry. OOS evaluator wajib menerapkan aturan yang sama agar
        # model tidak diuji pada kondisi yang tidak pernah diajarkan (entry tanpa trigger).
        TRIGGER_WINDOW = 30
        _flag_names_buy  = ['is_CSA_Buy',  'is_CSAK_Buy',  'is_CSM_Buy']
        _flag_names_sell = ['is_CSA_Sell', 'is_CSAK_Sell', 'is_CSM_Sell']

        _any_buy_flag  = any(c in df_calc.columns for c in _flag_names_buy)
        _any_sell_flag = any(c in df_calc.columns for c in _flag_names_sell)

        if _any_buy_flag or _any_sell_flag:
            # Gabungkan semua flag trigger buy/sell menjadi satu array boolean
            _trig_buy_raw = np.zeros(len(df_calc), dtype=np.float32)
            for _col in _flag_names_buy:
                if _col in df_calc.columns:
                    _trig_buy_raw = np.maximum(_trig_buy_raw, pd.to_numeric(df_calc[_col], errors='coerce').fillna(0).values.astype(np.float32))

            _trig_sell_raw = np.zeros(len(df_calc), dtype=np.float32)
            for _col in _flag_names_sell:
                if _col in df_calc.columns:
                    _trig_sell_raw = np.maximum(_trig_sell_raw, pd.to_numeric(df_calc[_col], errors='coerce').fillna(0).values.astype(np.float32))

            # Rolling sum pada 30 bar SEBELUM bar saat ini (shift(1) agar bar ini tidak dihitung sendiri)
            # has_trigger_buy[i] = True jika ada minimal 1 trigger buy di [i-30, i-1]
            _s_buy  = pd.Series(_trig_buy_raw)
            _s_sell = pd.Series(_trig_sell_raw)
            has_trigger_buy  = (_s_buy.shift(1).rolling(TRIGGER_WINDOW, min_periods=1).sum() > 0).values
            has_trigger_sell = (_s_sell.shift(1).rolling(TRIGGER_WINDOW, min_periods=1).sum() > 0).values

            logger.debug(
                f"[TRIGGER FILTER] Buy zone valid: {is_valid_buy.sum()} → setelah trigger filter: {(is_valid_buy & has_trigger_buy).sum()} | "
                f"Sell zone valid: {is_valid_sell.sum()} → setelah trigger filter: {(is_valid_sell & has_trigger_sell).sum()}"
            )
        else:
            # Fallback graceful: kolom flag tidak tersedia (mungkin data lama sebelum v2 indicators)
            # → tidak terapkan filter, biarkan semua zona lolos agar tidak memblokir evaluasi
            logger.warning(
                "[TRIGGER FILTER] Kolom flag CSA/CSAK/CSM tidak ditemukan di df_calc. "
                "Filter trigger dinonaktifkan (fallback graceful). Pastikan calculate_bbma_sequence_features() "
                "sudah dijalankan sebelum OOS evaluasi untuk hasil optimal."
            )
            has_trigger_buy  = np.ones(len(df_calc), dtype=bool)
            has_trigger_sell = np.ones(len(df_calc), dtype=bool)

        # 5. Threshold Masuk & Anti Counter-Trend Topography Guard
        cal_th = getattr(researcher, f"optimal_threshold_{mode_str}", 0.54) or 0.54
        if cal_th > 1.0:
            cal_th /= 100.0

        forbid_b = pd.to_numeric(df_calc['forbid_buy'], errors='coerce').fillna(0).values.astype(bool) if 'forbid_buy' in df_calc.columns else np.zeros(len(df_calc), dtype=bool)
        forbid_s = pd.to_numeric(df_calc['forbid_sell'], errors='coerce').fillna(0).values.astype(bool) if 'forbid_sell' in df_calc.columns else np.zeros(len(df_calc), dtype=bool)
        sq_b = pd.to_numeric(df_calc['is_squeeze_buy_allowed'], errors='coerce').fillna(1).values.astype(bool) if 'is_squeeze_buy_allowed' in df_calc.columns else np.ones(len(df_calc), dtype=bool)
        sq_s = pd.to_numeric(df_calc['is_squeeze_sell_allowed'], errors='coerce').fillna(1).values.astype(bool) if 'is_squeeze_sell_allowed' in df_calc.columns else np.ones(len(df_calc), dtype=bool)

        # Partisi Rezim Pasar Spesifik per Mode (Regime-Specialized Filtering)
        is_sq = pd.to_numeric(df_calc['is_bb_squeeze'], errors='coerce').fillna(0).values.astype(bool) if 'is_bb_squeeze' in df_calc.columns else np.zeros(len(df_calc), dtype=bool)
        is_exp = pd.to_numeric(df_calc['is_bb_expanding'], errors='coerce').fillna(0).values.astype(bool) if 'is_bb_expanding' in df_calc.columns else np.zeros(len(df_calc), dtype=bool)
        is_brk_b = pd.to_numeric(df_calc['is_breakout_bull'], errors='coerce').fillna(0).values.astype(bool) if 'is_breakout_bull' in df_calc.columns else np.zeros(len(df_calc), dtype=bool)
        is_brk_s = pd.to_numeric(df_calc['is_breakout_bear'], errors='coerce').fillna(0).values.astype(bool) if 'is_breakout_bear' in df_calc.columns else np.zeros(len(df_calc), dtype=bool)
        is_run_b = pd.to_numeric(df_calc['is_running_bull'], errors='coerce').fillna(0).values.astype(bool) if 'is_running_bull' in df_calc.columns else np.zeros(len(df_calc), dtype=bool)
        is_run_s = pd.to_numeric(df_calc['is_running_bear'], errors='coerce').fillna(0).values.astype(bool) if 'is_running_bear' in df_calc.columns else np.zeros(len(df_calc), dtype=bool)

        is_unified = mode_str in ("unified", "profit") or getattr(researcher, "model_unified", None) is not None or ('Target_Class' in df_calc.columns)
        if is_unified:
            buy_signals  = (p_buy >= cal_th) & (p_buy > p_sell)
            sell_signals = (p_sell >= cal_th) & (p_sell > p_buy)
        else:
            runner_regime_mask = is_brk_b | is_brk_s | is_run_b | is_run_s | (is_exp & ~is_sq)
            normal_regime_mask = is_sq | (~runner_regime_mask)
            regime_mask = runner_regime_mask if mode_str == "runner" else normal_regime_mask
            buy_signals  = (p_buy >= cal_th) & (p_buy >= p_sell) & is_valid_buy  & has_trigger_buy  & (~forbid_b) & sq_b & regime_mask
            sell_signals = (p_sell >= cal_th) & (p_sell >= p_buy) & is_valid_sell & has_trigger_sell & (~forbid_s) & sq_s & regime_mask

        # Resolusi sinyal ganda di bar yang sama (Mutual Exclusion via EMA 50)
        both_mask = buy_signals & sell_signals
        if np.any(both_mask):
            ema_val = df_calc['EMA_50'].values if 'EMA_50' in df_calc.columns else (df_calc['ema_50'].values if 'ema_50' in df_calc.columns else df_calc['close'].values)
            close_val = df_calc['close'].values
            buy_signals = buy_signals & (~both_mask | (close_val >= ema_val))
            sell_signals = sell_signals & (~both_mask | (close_val < ema_val))

        # 6. Kalkulasi SL & TP Adaptif per Candle dari ATR sesuai Profile
        close_prices = df_calc['close'].values
        sl_pct = np.clip((profile.sl_atr_mult * atrs) / np.maximum(close_prices, 1e-4), 0.0005, 0.15)

        if mode_str in ("normal", "unified", "profit"):
            target_rr = getattr(profile, 'rr_normal', 1.5)
        else:
            target_rr = getattr(profile, 'rr_runner', 3.5)
        tp_pct = np.clip((target_rr * profile.sl_atr_mult * atrs) / np.maximum(close_prices, 1e-4), 0.001, 0.80)

        # 7. Cooldown State Machine — mencegah spam sinyal di zona yang sama
        MIN_COOLDOWN_BARS = profile.min_cooldown_bars
        cooldown_remaining = 0
        buy_signals_filtered  = np.zeros(len(buy_signals), dtype=bool)
        sell_signals_filtered = np.zeros(len(sell_signals), dtype=bool)
        for idx_cd in range(len(buy_signals)):
            if cooldown_remaining > 0:
                cooldown_remaining -= 1
                continue
            if buy_signals[idx_cd]:
                buy_signals_filtered[idx_cd]  = True
                cooldown_remaining = MIN_COOLDOWN_BARS
            elif sell_signals[idx_cd]:
                sell_signals_filtered[idx_cd] = True
                cooldown_remaining = MIN_COOLDOWN_BARS
        buy_signals  = buy_signals_filtered
        sell_signals = sell_signals_filtered

        import vectorbt as vbt

        # Estimasi timeframe frekuensi dinamis dari indeks lilin
        freq_str = '5m'
        if isinstance(df_calc.index, pd.DatetimeIndex) and len(df_calc) > 2:
            try:
                median_delta = (pd.Series(df_calc.index[1:]) - pd.Series(df_calc.index[:-1])).median()
                minutes = max(1, int(median_delta.total_seconds() // 60))
                freq_str = f"{minutes}m"
            except Exception:
                freq_str = '5m'

        spread_fee = 0.00015 # Standar spread institusional ~30 poin pada emas/forex
        portfolio = vbt.Portfolio.from_signals(
            close=pd.Series(close_prices, index=df_calc.index),
            entries=pd.Series(buy_signals, index=df_calc.index),
            short_entries=pd.Series(sell_signals, index=df_calc.index),
            sl_stop=pd.Series(sl_pct, index=df_calc.index),
            tp_stop=pd.Series(tp_pct, index=df_calc.index),
            fees=spread_fee,
            freq=freq_str
        )

        stats = portfolio.stats()

        def safe_float(val: Any, default: float = 0.0, max_cap: float = 999.0) -> float:
            try:
                f = float(val)
                if np.isnan(f):
                    return default
                if np.isposinf(f):
                    return max_cap
                if np.isneginf(f):
                    return -max_cap
                return f
            except Exception:
                return default

        total_trades = int(safe_float(stats.get("Total Trades"), 0.0))
        win_rate = safe_float(stats.get("Win Rate [%]"), 0.0)
        profit_factor = safe_float(stats.get("Profit Factor"), 0.0, max_cap=999.0) if total_trades > 0 else 0.0
        sharpe_ratio = safe_float(stats.get("Sharpe Ratio"), 0.0, max_cap=99.0) if total_trades > 0 else 0.0
        max_dd = abs(safe_float(stats.get("Max Drawdown [%]"), 0.0))
        total_return = safe_float(stats.get("Total Return [%]"), 0.0)

        metrics = {
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "total_trades": total_trades,
            "total_return_pct": round(total_return, 2)
        }

        # 7b. TD Eradication: Hentikan auto-harvest trade rugi OOS ke Hard Negatives
        # Setup rugi pada backtest OOS adalah varians stokastik normal di pasar finansial.
        # Memanen trade rugi dan meng-override ground truth label menjadi 0 di training
        # berikutnya terbukti meracuni model dan memicu degradasi akurasi sekuensial.
        harvested_hn_count = 0
        losing_records = []

        # 8. Ekstraksi Kurva Ekuitas (downsampled to <= 100 points untuk visualisasi lightweight-charts)
        equity_curve = []
        try:
            val_series = portfolio.value()
            if val_series is not None and len(val_series) > 0:
                step = max(1, len(val_series) // 80)
                sub_series = val_series.iloc[::step]
                if sub_series.index[-1] != val_series.index[-1]:
                    sub_series = pd.concat([sub_series, val_series.iloc[[-1]]])
                for dt_idx, v in sub_series.items():
                    ts = 0
                    if hasattr(dt_idx, 'timestamp'):
                        ts = int(dt_idx.timestamp())
                    else:
                        try:
                            ts = int(pd.to_datetime(dt_idx).timestamp())
                        except Exception:
                            ts = 0
                    equity_curve.append({
                        "time": ts,
                        "value": round(float(v), 2)
                    })
        except Exception as e_eq:
            logger.debug(f"Gagal generate equity curve: {e_eq}")

        # 9. Evaluasi Keputusan Pass / Fail
        passed, checks, reasons = evaluate_metrics(metrics, base_criteria)

        scorecard = {
            "symbol": sym_clean,
            "mode": mode_str,
            "evaluated_at": now_str,
            "passed": passed,
            "threshold_used": round(float(cal_th), 4),
            "metrics": metrics,
            "criteria": base_criteria,
            "checks": checks,
            "reasons": reasons,
            "equity_curve": equity_curve,
            "harvested_hard_negatives": harvested_hn_count,
            "losing_records": losing_records
        }

        if passed:
            logger.info(
                f"[FIT & PROPER PASS] ✅ Model {mode_str.upper()} ({sym_clean}) LOLOS verifikasi finansial OOS! "
                f"WR: {win_rate:.1f}%, PF: {profit_factor:.2f}, Sharpe: {sharpe_ratio:.2f}, DD: {max_dd:.1f}%, Trades: {total_trades}"
            )
        else:
            logger.warning(
                f"[FIT & PROPER FAIL] ❌ Model {mode_str.upper()} ({sym_clean}) GAGAL uji OOS: {', '.join(reasons)}. "
                f"(WR: {win_rate:.1f}%, PF: {profit_factor:.2f}, Sharpe: {sharpe_ratio:.2f}, DD: {max_dd:.1f}%, Trades: {total_trades})"
            )

        return scorecard

    except Exception as e:
        logger.error(f"Error saat mengeksekusi run_fit_proper_test ({sym_clean} - {mode_str}): {e}", exc_info=True)
        return {
            "symbol": sym_clean,
            "mode": mode_str,
            "evaluated_at": now_str,
            "passed": False,
            "threshold_used": 0.0,
            "metrics": {
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "total_trades": 0,
                "total_return_pct": 0.0
            },
            "criteria": base_criteria,
            "checks": {k: False for k in ["win_rate_passed", "profit_factor_passed", "sharpe_ratio_passed", "drawdown_passed", "trades_passed"]},
            "reasons": [f"Terjadi error saat simulasi VectorBT: {str(e)}"]
        }
