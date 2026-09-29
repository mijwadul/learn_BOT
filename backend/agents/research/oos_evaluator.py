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

    # Ambil kriteria kelulusan
    base_criteria = FIT_PROPER_THRESHOLDS.get(mode_str, FIT_PROPER_THRESHOLDS["normal"]).copy()
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
        if hasattr(researcher, "generate_targets"):
            df_calc = researcher.generate_targets(df_calc)
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
            # Fallback ke kolom numerik yang tersedia
            model_features = [c for c in df_calc.columns if c not in ['open', 'high', 'low', 'close', 'tick_volume', 'Target_Normal', 'Target_Runner', 'setup_dir', 'symbol']]

        X_oos = df_calc.reindex(columns=model_features, fill_value=0.0).copy()
        for col in model_features:
            if not (pd.api.types.is_numeric_dtype(X_oos[col]) or pd.api.types.is_bool_dtype(X_oos[col])):
                X_oos[col] = pd.to_numeric(X_oos[col], errors='coerce').fillna(0.0)

        # 3. Prediksi Probabilitas Kemenangan
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X_oos)
            classes = list(getattr(model, 'classes_', [0, 1]))
            idx_w = classes.index(1) if 1 in classes else (1 if probs.shape[1] > 1 else 0)
            p_win = probs[:, idx_w] if probs.shape[1] > idx_w else probs[:, -1]
        elif hasattr(model, "predict"):
            p_win = model.predict(X_oos)
        else:
            raise ValueError("Model tidak memiliki method predict atau predict_proba")

        # 4. Filter Spasial Zona Re-entry BBMA LWMA
        lwma_low_zone = np.maximum(df_calc['LWMA_5_Low'].values, df_calc['LWMA_10_Low'].values) if 'LWMA_5_Low' in df_calc.columns else df_calc['low'].values
        lwma_high_zone = np.minimum(df_calc['LWMA_5_High'].values, df_calc['LWMA_10_High'].values) if 'LWMA_5_High' in df_calc.columns else df_calc['high'].values
        atrs = df_calc['ATR_14'].values if 'ATR_14' in df_calc.columns else np.full(len(df_calc), 0.001)
        atrs = np.where(np.isnan(atrs) | (atrs <= 0), 0.001, atrs)
        buffer = 0.35 * atrs

        is_valid_buy = (df_calc['low'].values <= (lwma_low_zone + buffer))
        is_valid_sell = (df_calc['high'].values >= (lwma_high_zone - buffer))

        # 5. Threshold Masuk
        cal_th = getattr(researcher, f"optimal_threshold_{mode_str}", 0.54) or 0.54
        if cal_th > 1.0:
            cal_th /= 100.0

        buy_signals = (p_win >= cal_th) & is_valid_buy
        sell_signals = (p_win >= cal_th) & is_valid_sell

        # Resolusi sinyal ganda di bar yang sama (Mutual Exclusion via EMA 50)
        both_mask = buy_signals & sell_signals
        if np.any(both_mask):
            ema_val = df_calc['EMA_50'].values if 'EMA_50' in df_calc.columns else df_calc['close'].values
            close_val = df_calc['close'].values
            buy_signals = buy_signals & (~both_mask | (close_val >= ema_val))
            sell_signals = sell_signals & (~both_mask | (close_val < ema_val))

        # 6. Kalkulasi SL & TP Adaptif per Candle dari ATR
        # PENTING: Formula SL harus identik dengan target_labeler v2 (1.2 * ATR)
        # agar label training dan simulasi VectorBT benar-benar konsisten.
        rr_ratio = 1.5 if mode_str == "normal" else getattr(researcher, "max_runner_rr", 5.0)
        close_prices = df_calc['close'].values
        sl_pct = np.clip((1.2 * atrs) / close_prices, 0.0005, 0.15)

        # TP dinamis: jika tersedia fractal_capacity_buy/sell, gunakan untuk scaling TP
        # Hal ini mencerminkan bahwa setup Re-entry H1 layak diberi TP lebih jauh dari M5.
        frac_cap_buy  = df_calc['fractal_capacity_buy'].values  if 'fractal_capacity_buy'  in df_calc.columns else np.full(len(df_calc), 1.0)
        frac_cap_sell = df_calc['fractal_capacity_sell'].values if 'fractal_capacity_sell' in df_calc.columns else np.full(len(df_calc), 1.0)
        # Rata-rata kapasitas buy & sell untuk tiap bar (bar bisa aktif keduanya)
        frac_cap = np.where(buy_signals, frac_cap_buy, np.where(sell_signals, frac_cap_sell, 1.0))
        # TP scaling: base_rr * fractal_capacity (1.0..3.0+)
        tp_pct = np.clip((rr_ratio * frac_cap * 1.2 * atrs) / close_prices, 0.001, 0.80)

        # 7. Cooldown State Machine — mencegah spam sinyal di zona yang sama
        # Setelah satu sinyal aktif, abaikan MIN_COOLDOWN_BARS berikutnya.
        MIN_COOLDOWN_BARS = 10  # ~50 menit di M5 setelah entry
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

        spread_fee = 0.00015 # Standar spread institusional ~30 poin pada emas/forex
        portfolio = vbt.Portfolio.from_signals(
            close=pd.Series(close_prices, index=df_calc.index),
            entries=pd.Series(buy_signals, index=df_calc.index),
            short_entries=pd.Series(sell_signals, index=df_calc.index),
            sl_stop=pd.Series(sl_pct, index=df_calc.index),
            tp_stop=pd.Series(tp_pct, index=df_calc.index),
            fees=spread_fee,
            freq='5m'
        )

        stats = portfolio.stats()

        def safe_float(val: Any, default: float = 0.0) -> float:
            try:
                f = float(val)
                return default if np.isnan(f) else f
            except Exception:
                return default

        win_rate = safe_float(stats.get("Win Rate [%]"), 0.0)
        profit_factor = safe_float(stats.get("Profit Factor"), 0.0)
        sharpe_ratio = safe_float(stats.get("Sharpe Ratio"), 0.0)
        max_dd = abs(safe_float(stats.get("Max Drawdown [%]"), 0.0))
        total_trades = int(safe_float(stats.get("Total Trades"), 0.0))
        total_return = safe_float(stats.get("Total Return [%]"), 0.0)

        metrics = {
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2) if not np.isinf(profit_factor) else 999.0,
            "sharpe_ratio": round(sharpe_ratio, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "total_trades": total_trades,
            "total_return_pct": round(total_return, 2)
        }

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
            "equity_curve": equity_curve
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
