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
    is_multiclass = 2 in classes
    if is_multiclass:
        idx_buy = classes.index(1) if 1 in classes else 1
        idx_sell = classes.index(2) if 2 in classes else 2
        p_buy = probs[:, idx_buy]
        p_sell = probs[:, idx_sell]
    else:
        idx_win = classes.index(1) if 1 in classes else (1 if probs.shape[1] > 1 else 0)
        p_win = probs[:, idx_win] if probs.shape[1] > idx_win else probs[:, -1]

    rr_ratio = profile.rr_normal if mode == 'normal' else profile.rr_runner
    target_wr = (profile.oos_criteria_normal["min_win_rate"] if mode == 'normal' else profile.oos_criteria_runner["min_win_rate"]) / 100.0
    min_crit_wr = target_wr
    min_crit_pf = (profile.oos_criteria_normal["min_profit_factor"] if mode == 'normal' else profile.oos_criteria_runner["min_profit_factor"])

    best_score = -999.0
    best_th = 0.50 if mode == 'runner' else 0.54
    best_stats = {}

    # Hapus filter rezim kaku lama (is_bb_squeeze); evaluasi murni pada seluruh data validasi
    regime_filter = np.ones(len(X_cal), dtype=bool)

    candidate_thresholds = np.linspace(0.38, 0.65, 28)
    effective_min_signals = max(min_signals, 15)

    for th in candidate_thresholds:
        if is_multiclass:
            buy_trade = (p_buy >= th) & (p_buy > p_sell)
            sell_trade = (p_sell >= th) & (p_sell > p_buy)
            n_trades = int(buy_trade.sum() + sell_trade.sum())
            if n_trades < effective_min_signals:
                continue

            wins = int((buy_trade & (y_cal == 1)).sum() + (sell_trade & (y_cal == 2)).sum())
            losses = n_trades - wins
            # TD-07 Asymmetric penalty: rugi salah arah bobotnya 2.5R
            opp_losses = int((buy_trade & (y_cal == 2)).sum() + (sell_trade & (y_cal == 1)).sum())
            chop_losses = losses - opp_losses
            gross_profit = wins * 1.5
            gross_loss = max(chop_losses * 1.0 + opp_losses * 2.5, 0.001)
        else:
            pred_trade = (p_win >= th)
            n_trades = int(pred_trade.sum())
            if n_trades < effective_min_signals:
                continue
            wins = int((pred_trade & (y_cal == 1)).sum())
            losses = n_trades - wins
            gross_profit = wins * rr_ratio
            gross_loss = max(losses * 1.0, 0.001)

        wr = wins / n_trades
        pf = gross_profit / gross_loss
        expectancy = (gross_profit - gross_loss) / n_trades

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
