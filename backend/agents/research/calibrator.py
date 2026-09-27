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
    max_runner_rr: float = 5.0
) -> float:
    """
    Post-Training Dynamic Threshold Calibration (Binary Meta-Model):
    Mengkalibrasi ambang batas probabilitas (optimal entry threshold) langsung pada model
    yang telah dilatih utuh menggunakan validation slice kronologis akhir.
    Menjamin ambang batas menghasilkan volume sinyal yang sehat dan memaksimalkan Expectancy (+R) & Win Rate.
    """
    if model is None or X is None or len(X) == 0:
        return 0.54 if mode == 'normal' else 0.50

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

    rr_ratio = 2.0 if mode == 'normal' else max_runner_rr
    target_wr = 0.50 if mode == 'normal' else 0.25

    best_score = -999.0
    best_th = 0.52 if mode == 'runner' else 0.54
    best_stats = {}

    # Candidate threshold disesuaikan dengan profil mode:
    # Normal (RR 1:2): butuh akurasi >= 50%
    # Runner (RR 1:5): target akurasi 30-40% dengan volume perdagangan sehat
    if mode == 'runner':
        candidate_thresholds = np.linspace(0.45, 0.55, 21)
        effective_min_signals = max(min_signals, int(len(X_cal) * 0.01))
    else:
        candidate_thresholds = np.linspace(0.535, 0.63, 20)
        effective_min_signals = max(min_signals, int(len(X_cal) * 0.005))

    for th in candidate_thresholds:
        pred_trade = p_win >= th
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

        # Penalti keras jika akurasi di bawah standar kelulusan institusional (Normal: 50%, Runner: 25%)
        wr_penalty = 0.0
        if mode == 'normal' and wr < 0.50:
            wr_penalty = (0.50 - wr) * 20.0
        elif mode == 'runner' and wr < 0.25:
            wr_penalty = (0.25 - wr) * 20.0

        # Penalti sampel kecil & bonus signifikansi statistik (SQN proxy)
        sample_weight_factor = min(1.0, n_trades / 120.0)
        sqn_proxy = (expectancy / max(1.0, np.sqrt(rr_ratio))) * np.sqrt(min(n_trades, 500)) / 10.0
        score = (((expectancy * 2.0) + ((wr - target_wr) * 2.5) + (min(pf, 3.0) * 0.2) - wr_penalty) * sample_weight_factor) + sqn_proxy

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
