import logging
import numpy as np
import pandas as pd
from typing import Optional, Any

logger = logging.getLogger(__name__)

def calibrate_optimal_threshold(
    model: Any,
    X: pd.DataFrame,
    y: Any,
    mode: str = "normal",
    setup_directions: Optional[np.ndarray] = None,
    min_signals: int = 25,
    max_runner_rr: float = 5.0,
    symbol: str = "XAUUSD"
) -> float:
    """
    Post-Training Dynamic Threshold Calibration (Binary Meta-Model):
    Mengkalibrasi ambang batas probabilitas (optimal entry threshold) langsung pada model
    yang telah dilatih utuh menggunakan validation slice kronologis akhir.
    Menjamin ambang batas menghasilkan volume sinyal yang sehat dan memaksimalkan Expectancy (+R) & Win Rate.
    """
    if model is None or X is None or len(X) == 0:
        return 0.50 if mode == 'runner' else 0.54

    from .profiles import get_profile
    profile = get_profile(symbol)

    n = len(X)
    cal_start = int(n * 0.75)
    X_cal = X.iloc[cal_start:].copy()
    y_cal = np.array(y.iloc[cal_start:] if hasattr(y, 'iloc') else y[cal_start:], dtype=int)

    if len(X_cal) < 50:
        X_cal = X
        y_cal = np.array(y, dtype=int)

    probs = model.predict_proba(X_cal)
    classes = list(getattr(model, 'classes_', [0, 1]))
    idx_win = classes.index(1) if 1 in classes else (1 if probs.shape[1] > 1 else 0)
    p_win = probs[:, idx_win] if probs.shape[1] > idx_win else probs[:, -1]

    rr_ratio = profile.rr_normal if mode == 'normal' else profile.rr_runner
    target_wr = (profile.oos_criteria_normal["min_win_rate"] if mode == 'normal' else profile.oos_criteria_runner["min_win_rate"]) / 100.0
    min_crit_wr = target_wr
    min_crit_pf = (profile.oos_criteria_normal["min_profit_factor"] if mode == 'normal' else profile.oos_criteria_runner["min_profit_factor"])

    best_score = -999.0
    best_th = 0.50 if mode == 'runner' else 0.54
    best_stats = {}

    # Filter habitat rezim saat kalibrasi
    if mode == 'runner':
        col_rb = 'is_running_bull' if 'is_running_bull' in X_cal.columns else ('feat_is_running_bull' if 'feat_is_running_bull' in X_cal.columns else None)
        col_rs = 'is_running_bear' if 'is_running_bear' in X_cal.columns else ('feat_is_running_bear' if 'feat_is_running_bear' in X_cal.columns else None)
        col_bb = 'is_breakout_bull' if 'is_breakout_bull' in X_cal.columns else ('feat_is_breakout_bull' if 'feat_is_breakout_bull' in X_cal.columns else None)
        col_bs = 'is_breakout_bear' if 'is_breakout_bear' in X_cal.columns else ('feat_is_breakout_bear' if 'feat_is_breakout_bear' in X_cal.columns else None)

        f_run_b = (X_cal[col_rb] == 1) if col_rb else np.zeros(len(X_cal), dtype=bool)
        f_run_s = (X_cal[col_rs] == 1) if col_rs else np.zeros(len(X_cal), dtype=bool)
        f_brk_b = (X_cal[col_bb] == 1) if col_bb else np.zeros(len(X_cal), dtype=bool)
        f_brk_s = (X_cal[col_bs] == 1) if col_bs else np.zeros(len(X_cal), dtype=bool)
        feat_run = (f_run_b | f_run_s | f_brk_b | f_brk_s)

        if feat_run.sum() >= 10:
            regime_filter = feat_run.values if hasattr(feat_run, 'values') else np.array(feat_run, dtype=bool)
        else:
            regime_filter = np.ones(len(X_cal), dtype=bool)
    else:
        col_sq = 'is_bb_squeeze' if 'is_bb_squeeze' in X_cal.columns else ('feat_is_bb_squeeze' if 'feat_is_bb_squeeze' in X_cal.columns else None)
        f_sq = (X_cal[col_sq] == 1) if col_sq else np.zeros(len(X_cal), dtype=bool)
        if f_sq.sum() >= 10:
            regime_filter = f_sq.values if hasattr(f_sq, 'values') else np.array(f_sq, dtype=bool)
        else:
            regime_filter = np.ones(len(X_cal), dtype=bool)

    # Candidate threshold disesuaikan dengan profil instrumen:
    if mode == 'runner':
        candidate_thresholds = np.linspace(0.35, 0.65, 31)
        effective_min_signals = max(min_signals, int(regime_filter.sum() * 0.02))
    else:
        candidate_thresholds = np.linspace(0.42, 0.70, 29)
        effective_min_signals = max(min_signals, int(regime_filter.sum() * 0.02))

    for th in candidate_thresholds:
        pred_trade = (p_win >= th) & regime_filter
        n_trades = int(pred_trade.sum())
        if n_trades < effective_min_signals:
            continue

        wins = int((pred_trade & (y_cal == 1)).sum())
        losses = n_trades - wins
        wr = wins / n_trades
        gross_profit = wins * rr_ratio
        gross_loss = max(losses * 1.0, 0.001)
        pf = gross_profit / gross_loss
        expectancy = (wr * rr_ratio) - ((1.0 - wr) * 1.0)

        # Penalti keras jika metrik di bawah standar kelulusan profile
        wr_penalty = 0.0
        if wr < min_crit_wr:
            wr_penalty = (min_crit_wr - wr) * 25.0

        pf_penalty = 0.0
        if pf < min_crit_pf:
            pf_penalty = (min_crit_pf - pf) * 10.0

        # Penalti sampel kecil & bonus signifikansi statistik (SQN proxy)
        sample_weight_factor = min(1.0, n_trades / 120.0)
        sqn_proxy = (expectancy / max(1.0, np.sqrt(rr_ratio))) * np.sqrt(min(n_trades, 500)) / 10.0
        score = (((expectancy * 2.0) + ((wr - target_wr) * 2.5) + (min(pf, 3.0) * 0.2) - wr_penalty - pf_penalty) * sample_weight_factor) + sqn_proxy

        if score > best_score:
            best_score = score
            best_th = float(th)
            best_stats = {
                "signals": n_trades,
                "win_rate": wr,
                "profit_factor": pf,
                "expectancy": expectancy
            }

    if best_stats:
        logger.info(
            f"[{mode.upper()} THRESHOLD CALIBRATED] 🎯 Ambang batas dikalibrasi pada {len(X_cal):,} sampel akhir:\n"
            f"   • Optimal Entry Threshold: {best_th*100:.1f}%\n"
            f"   • Validasi Sampel: {best_stats['signals']:,} sinyal | "
            f"WR: {best_stats['win_rate']*100:.1f}% | PF: {best_stats['profit_factor']:.2f} | "
            f"Expectancy: {best_stats['expectancy']:+.2f}R"
        )
    else:
        logger.warning(f"[{mode.upper()} THRESHOLD CALIBRATION] Fallback threshold: {best_th*100:.1f}%.")

    return best_th
