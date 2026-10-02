import logging
import numpy as np
import pandas as pd
import optuna
import lightgbm as lgb
from sklearn.metrics import average_precision_score
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

def build_purged_folds(n_samples: int, purge_len: int = 150) -> List[Tuple[int, int, int, int]]:
    """
    Membangun Purged Walk-Forward Time-Series CV splits (CPCV Framework).
    Purge window 150 bar mencegah label leakage antara fold latih dan fold validasi.
    """
    folds = []
    if n_samples >= 300:
        f1_tr_end = int(n_samples * 0.40)
        f1_val_st = min(n_samples - 25, f1_tr_end + purge_len)
        f1_val_en = min(n_samples, int(n_samples * 0.60))
        if f1_val_en - f1_val_st >= 20:
            folds.append((0, f1_tr_end, f1_val_st, f1_val_en))

        f2_tr_end = int(n_samples * 0.60)
        f2_val_st = min(n_samples - 25, f2_tr_end + purge_len)
        f2_val_en = min(n_samples, int(n_samples * 0.80))
        if f2_val_en - f2_val_st >= 20:
            folds.append((0, f2_tr_end, f2_val_st, f2_val_en))

        f3_tr_end = int(n_samples * 0.75)
        f3_val_st = min(n_samples - 25, f3_tr_end + purge_len)
        f3_val_en = n_samples
        if f3_val_en - f3_val_st >= 20:
            folds.append((0, f3_tr_end, f3_val_st, f3_val_en))

    if not folds:
        split_idx = int(n_samples * 0.75)
        train_end = max(20, split_idx - purge_len)
        folds.append((0, train_end, split_idx, n_samples))

    return folds


def optimize_hyperparameters(
    X: pd.DataFrame,
    y: Any,
    sample_weights: Any,
    mode: str = "normal",
    n_trials: int = 40,
    setup_directions: Optional[np.ndarray] = None,
    symbol: str = "XAUUSD",
    max_runner_rr: float = 5.0
) -> Dict[str, Any]:
    """
    Optuna Auto-Tuning berbasis Purged Walk-Forward Cross Validation.
    Memaksimalkan Expectancy (+R), Win Rate, PR-AUC, dan kestabilan Profit Factor.
    """
    mode_str = mode.lower()
    y = np.array(y, dtype=int)
    sample_weights = np.array(sample_weights, dtype=float)
    n_samples = len(X)

    from .profiles import get_profile
    profile = get_profile(symbol)
    rr_ratio = profile.rr_runner if mode_str == "runner" else profile.rr_normal
    target_wr = (profile.oos_criteria_runner["min_win_rate"] if mode_str == 'runner' else profile.oos_criteria_normal["min_win_rate"]) / 100.0

    logger.info(f"[{mode_str.upper()} OPTUNA START] 🔬 Memulai Purged Walk-Forward CV & Meta-Model Auto-Tuning ({n_trials} Trials) untuk {symbol}...")
    logger.info(f"[{mode_str.upper()} OPTUNA METRIK] 🎯 Target: Precision (WR >= {target_wr*100:.0f}%) + Expectancy (+R) + PR-AUC pada RR 1:{rr_ratio:.1f}")

    # TD#5 FIX: Purge window dinaikkan 150 → 250 bar (~21 jam di M5).
    # Satu siklus BBMA penuh (Extrem → TPW → MHV → CSA/CSAK → Re-entry) bisa makan
    # 200–250 candle. Window 150 bar berisiko label leakage ringan antar fold yang membuat
    # skor Optuna tampak lebih bagus dari kenyataannya di data OOS.
    folds = build_purged_folds(n_samples, purge_len=250)
    logger.info(f"[{mode.upper()} OPTUNA CV] Membentuk {len(folds)} Purged Walk-Forward Folds (Total: {n_samples:,} baris setup).")

    best_so_far = -10.0
    best_threshold_so_far = 0.48 if mode == 'runner' else 0.52

    def objective(trial):
        nonlocal best_so_far, best_threshold_so_far
        trial_num = trial.number + 1

        cw_choice = trial.suggest_categorical('class_weight', [None, 'balanced'])

        params = {
            'n_estimators': trial.suggest_int('n_estimators', 100, 300),
            'learning_rate': trial.suggest_float('learning_rate', 0.015, 0.06, log=True),
            'max_depth': trial.suggest_int('max_depth', 3, 6),
            'num_leaves': trial.suggest_int('num_leaves', 12, 35),
            'min_child_samples': trial.suggest_int('min_child_samples', 30, 200),
            'subsample': trial.suggest_float('subsample', 0.65, 0.95),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.60, 0.95),
            'colsample_bynode': trial.suggest_float('colsample_bynode', 0.50, 0.90),
            'extra_trees': trial.suggest_categorical('extra_trees', [True, False]),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-2, 10.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-2, 10.0, log=True),
            'min_split_gain': trial.suggest_float('min_split_gain', 0.0, 0.5),
            'objective': 'binary',
            'class_weight': cw_choice,
            'random_state': 42,
            'verbose': -1
        }

        trial_threshold = trial.suggest_float('entry_threshold', 0.35, 0.65) if mode == 'runner' else trial.suggest_float('entry_threshold', 0.42, 0.70)

        fold_scores = []
        fold_wrs = []
        fold_signals = []
        fold_exp = []
        fold_pf = []

        for tr_st, tr_en, val_st, val_en in folds:
            X_tr = X.iloc[tr_st:tr_en]
            y_tr = y[tr_st:tr_en]
            sw_tr = sample_weights[tr_st:tr_en]

            X_va = X.iloc[val_st:val_en]
            y_va = y[val_st:val_en]
            sw_va = sample_weights[val_st:val_en]

            if len(np.unique(y_tr)) < 2:
                continue

            model = lgb.LGBMClassifier(**params)
            model.fit(X_tr, y_tr, sample_weight=sw_tr)

            if hasattr(model, 'predict_proba'):
                probs_raw = model.predict_proba(X_va)
                classes = list(getattr(model, 'classes_', [0, 1]))
                idx_win = classes.index(1) if 1 in classes else (1 if probs_raw.shape[1] > 1 else 0)
                p_win = probs_raw[:, idx_win] if probs_raw.shape[1] > idx_win else probs_raw[:, -1]
            else:
                p_win = model.predict(X_va)

            # Filter habitat rezim saat evaluasi Optuna
            if mode_str == 'runner':
                col_rb = 'is_running_bull' if 'is_running_bull' in X_va.columns else ('feat_is_running_bull' if 'feat_is_running_bull' in X_va.columns else None)
                col_rs = 'is_running_bear' if 'is_running_bear' in X_va.columns else ('feat_is_running_bear' if 'feat_is_running_bear' in X_va.columns else None)
                col_bb = 'is_breakout_bull' if 'is_breakout_bull' in X_va.columns else ('feat_is_breakout_bull' if 'feat_is_breakout_bull' in X_va.columns else None)
                col_bs = 'is_breakout_bear' if 'is_breakout_bear' in X_va.columns else ('feat_is_breakout_bear' if 'feat_is_breakout_bear' in X_va.columns else None)

                f_run_b = (X_va[col_rb] == 1) if col_rb else np.zeros(len(X_va), dtype=bool)
                f_run_s = (X_va[col_rs] == 1) if col_rs else np.zeros(len(X_va), dtype=bool)
                f_brk_b = (X_va[col_bb] == 1) if col_bb else np.zeros(len(X_va), dtype=bool)
                f_brk_s = (X_va[col_bs] == 1) if col_bs else np.zeros(len(X_va), dtype=bool)
                reg_mask = (f_run_b | f_run_s | f_brk_b | f_brk_s)
                regime_filter = reg_mask.values if hasattr(reg_mask, 'values') else np.array(reg_mask, dtype=bool)
            else:
                col_sq = 'is_bb_squeeze' if 'is_bb_squeeze' in X_va.columns else ('feat_is_bb_squeeze' if 'feat_is_bb_squeeze' in X_va.columns else None)
                f_sq = (X_va[col_sq] == 1) if col_sq else np.zeros(len(X_va), dtype=bool)
                regime_filter = f_sq.values if hasattr(f_sq, 'values') else np.array(f_sq, dtype=bool)

            if np.sum(regime_filter) < 5:
                regime_filter = np.ones(len(X_va), dtype=bool)

            pred_trades = (p_win >= trial_threshold) & regime_filter
            n_tr = int(pred_trades.sum())
            fold_signals.append(n_tr)

            if n_tr >= 5:
                wins = int((y_va[pred_trades] == 1).sum())
                losses = n_tr - wins
                wr = wins / n_tr
                gp = wins * rr_ratio
                gl = max(losses * 1.0, 0.001)
                pf = gp / gl
                exp = (wr * rr_ratio) - ((1.0 - wr) * 1.0)

                try:
                    pr_auc = float(average_precision_score(y_va, p_win, sample_weight=sw_va))
                except Exception:
                    pr_auc = 0.50

                f_score = (exp * 2.0) + ((wr - target_wr) * 2.5) + (min(pf, 3.0) * 0.2) + (pr_auc * 0.3)
                fold_scores.append(f_score)
                fold_wrs.append(wr)
                fold_exp.append(exp)
                fold_pf.append(pf)
            elif n_tr > 0:
                wins = int((y_va[pred_trades] == 1).sum())
                wr = wins / n_tr
                fold_scores.append(-2.0 + wr)
                fold_wrs.append(wr)
                fold_exp.append(-0.5)
                fold_pf.append(0.5)
            else:
                fold_scores.append(-4.0)
                fold_wrs.append(0.0)
                fold_exp.append(-1.0)
                fold_pf.append(0.0)

        if fold_scores:
            trial_score = float(np.mean(fold_scores))
            avg_wr = float(np.mean(fold_wrs)) if fold_wrs else 0.0
            total_sig = int(np.sum(fold_signals))
            avg_exp = float(np.mean(fold_exp)) if fold_exp else 0.0
            avg_pf = float(np.mean(fold_pf)) if fold_pf else 0.0
        else:
            trial_score = -5.0
            avg_wr = 0.0
            total_sig = 0
            avg_exp = -1.0
            avg_pf = 0.0

        is_new_best = trial_score > best_so_far
        if is_new_best:
            best_so_far = trial_score
            best_threshold_so_far = trial_threshold

        star = " ⭐ [BEST BARU]" if is_new_best else ""
        cw_tag = "balanced" if cw_choice == 'balanced' else "natural"
        p_str = (
            f"lr={params['learning_rate']:.3f} | d={params['max_depth']} | "
            f"leaf={params['num_leaves']} | child={params['min_child_samples']} | "
            f"cw={cw_tag} | xtree={params['extra_trees']}"
        )
        logger.info(
            f"[{mode.upper()} OPTUNA #{trial_num:02d}/{n_trials}] {p_str} => "
            f"Thresh: {trial_threshold*100:.1f}% | Sinyal: {total_sig} (WR: {avg_wr*100:.1f}%, PF: {avg_pf:.2f}, Exp: {avg_exp:+.2f}R) | "
            f"Skor: {trial_score:.4f}{star}"
        )
        return trial_score

    study = optuna.create_study(direction='maximize')
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(objective, n_trials=n_trials)

    best_t = study.best_trial
    chosen_threshold = best_t.params.get('entry_threshold', best_threshold_so_far)

    best_params_clean = study.best_params.copy()
    best_params_clean['optimal_threshold'] = float(chosen_threshold)

    logger.info(
        f"🏆 [{mode.upper()} OPTUNA SELESAI] Hasil Terbaik dari {n_trials} Trials:\n"
        f"   - Trial Terpilih: #{best_t.number + 1}\n"
        f"   - Skor Optimasi (WR & Expectancy): {best_t.value:.4f}\n"
        f"   - Optimal Entry Threshold Terpilih: {chosen_threshold*100:.1f}%\n"
        f"   - Hyperparameters: {best_params_clean}"
    )

    return best_params_clean


def optimize_unified_multiclass(
    X: pd.DataFrame,
    y: Any,
    sample_weights: Optional[np.ndarray] = None,
    n_trials: int = 25,
    symbol: str = "XAUUSD"
) -> Dict[str, Any]:
    """
    Optuna Auto-Tuning untuk Model Tunggal Multiclass (0=Neutral, 1=BUY, 2=SELL).
    Memaksimalkan Out-of-Fold Profit Factor, Expectancy (+R), dan Win Rate
    menggunakan Purged Walk-Forward Cross Validation.
    """
    y = np.array(y, dtype=int)
    n_samples = len(X)
    folds = build_purged_folds(n_samples, purge_len=150)

    logger.info(f"🔬 [OPTUNA UNIFIED] Memulai Tuning Hyperparameter Multiclass ({n_trials} Trials) untuk {symbol}...")
    logger.info(f"   CV Splits: {len(folds)} Purged Folds pada {n_samples:,} baris.")

    best_score = -999.0
    best_threshold = 0.45

    def objective(trial):
        nonlocal best_score, best_threshold

        params = {
            'n_estimators': trial.suggest_int('n_estimators', 80, 250),
            'learning_rate': trial.suggest_float('learning_rate', 0.015, 0.08, log=True),
            'max_depth': trial.suggest_int('max_depth', 3, 6),
            'num_leaves': trial.suggest_int('num_leaves', 15, 45),
            'min_child_samples': trial.suggest_int('min_child_samples', 20, 150),
            'subsample': trial.suggest_float('subsample', 0.65, 0.95),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.60, 0.95),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-2, 5.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-2, 5.0, log=True),
            'objective': 'multiclass',
            'num_class': 3,
            'random_state': 42,
            'verbose': -1,
            'n_jobs': -1
        }
        trial_threshold = trial.suggest_float('entry_threshold', 0.40, 0.58)

        fold_scores = []
        fold_pfs = []
        fold_wrs = []
        fold_trades = []

        for (tr_s, tr_e, va_s, va_e) in folds:
            X_tr, y_tr = X.iloc[tr_s:tr_e], y[tr_s:tr_e]
            X_va, y_va = X.iloc[va_s:va_e], y[va_s:va_e]

            # Lewati jika kelas tidak representatif
            unique_classes = set(y_tr)
            if len(unique_classes) < 2:
                continue

            sw_tr = sample_weights[tr_s:tr_e] if sample_weights is not None else None
            clf = lgb.LGBMClassifier(**params)
            clf.fit(X_tr, y_tr, sample_weight=sw_tr)

            probs = clf.predict_proba(X_va)
            classes = list(getattr(clf, 'classes_', [0, 1, 2]))
            idx_b = classes.index(1) if 1 in classes else -1
            idx_s = classes.index(2) if 2 in classes else -1

            p_b = probs[:, idx_b] if idx_b >= 0 else np.zeros(len(X_va))
            p_s = probs[:, idx_s] if idx_s >= 0 else np.zeros(len(X_va))

            buy_sig = (p_b >= trial_threshold) & (p_b > p_s)
            sell_sig = (p_s >= trial_threshold) & (p_s > p_b)

            wins = 0
            losses = 0
            gross_p = 0.0
            gross_l = 0.0

            for i in range(len(y_va)):
                act = y_va[i]
                if buy_sig[i]:
                    if act == 1:
                        wins += 1
                        gross_p += 1.5
                    elif act == 2:
                        # TD-07: Penalti asimetris berat jika model memprediksi BUY saat pasar crashing (SELL)
                        losses += 1
                        gross_l += 2.5
                    else:
                        losses += 1
                        gross_l += 1.0
                elif sell_sig[i]:
                    if act == 2:
                        wins += 1
                        gross_p += 1.5
                    elif act == 1:
                        # TD-07: Penalti asimetris berat jika model memprediksi SELL saat pasar rally (BUY)
                        losses += 1
                        gross_l += 2.5
                    else:
                        losses += 1
                        gross_l += 1.0

            trades = wins + losses
            fold_trades.append(trades)
            if trades >= 3:
                wr = wins / trades
                pf = gross_p / max(1e-4, gross_l)
                exp = (gross_p - gross_l) / trades
                score = (pf - 1.0) * min(trades / 15.0, 1.0) + exp + (wr - 0.40)
                fold_scores.append(score)
                fold_pfs.append(pf)
                fold_wrs.append(wr)
            else:
                fold_scores.append(-2.0)
                fold_pfs.append(0.5)
                fold_wrs.append(0.0)

        if fold_scores:
            avg_score = float(np.mean(fold_scores))
            avg_pf = float(np.mean(fold_pfs))
            avg_wr = float(np.mean(fold_wrs))
            total_tr = sum(fold_trades)
        else:
            avg_score = -5.0
            avg_pf = 0.0
            avg_wr = 0.0
            total_tr = 0

        if avg_score > best_score:
            best_score = avg_score
            best_threshold = trial_threshold

        return avg_score

    study = optuna.create_study(direction='maximize')
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(objective, n_trials=n_trials)

    best_p = study.best_params.copy()
    opt_thresh = best_p.pop('entry_threshold', best_threshold)
    best_p['optimal_threshold'] = float(opt_thresh)

    logger.info(
        f"🏆 [OPTUNA UNIFIED SELESAI] Best Score={study.best_value:.4f} | "
        f"Optimal Threshold={opt_thresh*100:.1f}%\n"
        f"   Hyperparameters: {best_p}"
    )
    return best_p
