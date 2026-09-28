import logging
import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score

logging.basicConfig(level=logging.INFO)

class GatekeeperAgent:
    """
    Agent 3: The Gatekeeper (Out-of-Sample Validator - Institutional Standard)
    Menolak model yang overfitting melalui Chunked OOS Validation berbasis
    Institutional Quantitative Metrics (Precision, Profit Factor, Expectancy, Max Drawdown).
    """
    
    def __init__(self, researcher_agent):
        self.researcher = researcher_agent
        self.last_metrics = {
            "normal": {},
            "runner": {}
        }

    def validate_model(self, mode: str, test_generator, total_test_chunks: int) -> float:
        """
        Melakukan validasi model menggunakan test data generator.
        Mengevaluasi metrik institusional (Trade Precision, Profit Factor, Expectancy)
        dan mencatat hard negatives ke DB.
        Mengembalikan skor validasi terbobot (0.0 - 1.0) yang kompatibel dengan supervisor.
        """
        logging.info(f"Memulai validasi Out-Of-Sample (OOS) Institusional [{mode.capitalize()} Mode]...")
        
        model = self.researcher.model_normal if mode == 'normal' else self.researcher.model_runner
        if model is None:
            logging.error(f"Model {mode} belum dilatih.")
            return 0.0
            
        all_y_true = []
        all_y_pred = []
        test_chunk_idx = 1
        
        for df_test in test_generator:
            if df_test.empty:
                continue
            logging.info(f"[{mode.capitalize()} Mode] Validasi OOS Chunk {test_chunk_idx}/{total_test_chunks}...")
            # Purged Embargo: drop 100 candle perbatasan antara dataset train dan OOS untuk mencegah label leakage
            if test_chunk_idx == 1 and len(df_test) > 150:
                df_test = df_test.iloc[100:].copy()
            df_test = self.researcher.generate_targets(df_test)
            df_test = self.researcher.add_normalized_features(df_test)
            
            # Filter spasial zona Re-entry BBMA LWMA (Selaras dengan Target Labeler)
            lwma_low_zone = np.maximum(df_test['LWMA_5_Low'].values, df_test['LWMA_10_Low'].values)
            lwma_high_zone = np.minimum(df_test['LWMA_5_High'].values, df_test['LWMA_10_High'].values)
            atr_test = df_test['ATR_14'].values if 'ATR_14' in df_test.columns else np.full(len(df_test), 0.001)
            buffer = 0.35 * atr_test

            reentry_buy_mask = (df_test['low'].values <= (lwma_low_zone + buffer))
            reentry_sell_mask = (df_test['high'].values >= (lwma_high_zone - buffer))
            df_test = df_test[reentry_buy_mask | reentry_sell_mask].copy()

            
            if df_test.empty:
                continue
            
            # Pastikan kelengkapan kolom fitur sesuai model
            model_features = []
            if hasattr(model, 'feature_name_') and model.feature_name_ is not None:
                model_features = list(model.feature_name_)
            elif hasattr(model, 'booster_') and hasattr(model.booster_, 'feature_name'):
                model_features = list(model.booster_.feature_name())
            if not model_features:
                model_features = self.researcher.get_model_features(model, mode=mode)

            X_test = df_test.reindex(columns=model_features, fill_value=0.0).copy()
            for col in model_features:
                if not (pd.api.types.is_numeric_dtype(X_test[col]) or pd.api.types.is_bool_dtype(X_test[col])):
                    X_test[col] = pd.to_numeric(X_test[col], errors='coerce').fillna(0.0)

            target_col = 'Target_Normal' if mode == 'normal' else 'Target_Runner'
            y_test = df_test[target_col]
            
            # Evaluasi probabilitas menggunakan batas threshold AI (dinamis membaca konfigurasi dari SettingsManager / Config)
            from config import Config
            current_symbol = getattr(self.researcher, 'symbol', getattr(self, 'symbol', None))
            th_pct = Config.get_ai_threshold(symbol=current_symbol, mode=mode)
            default_th = th_pct / 100.0 if th_pct > 1.0 else th_pct
            if mode == 'runner':
                entry_thresh = getattr(self.researcher, 'optimal_threshold_runner', None) or default_th
            else:
                entry_thresh = getattr(self.researcher, 'optimal_threshold_normal', None) or default_th
            
            if hasattr(model, 'predict_proba'):
                probs = model.predict_proba(X_test)
                classes = list(getattr(model, 'classes_', [0, 1]))
                is_binary = (len(classes) == 2 or probs.shape[1] == 2)

                low_vals = df_test['low'].values if 'low' in df_test.columns else df_test['close'].values
                high_vals = df_test['high'].values if 'high' in df_test.columns else df_test['close'].values
                lwma_low_zone = np.maximum(df_test['LWMA_5_Low'].values, df_test['LWMA_10_Low'].values) if 'LWMA_5_Low' in df_test.columns else None
                lwma_high_zone = np.minimum(df_test['LWMA_5_High'].values, df_test['LWMA_10_High'].values) if 'LWMA_5_High' in df_test.columns else None
                atrs = df_test['ATR_14'].values if 'ATR_14' in df_test.columns else np.full(len(df_test), 0.001)
                buffer_zone = 0.35 * atrs

                # Pemicu Spasial Dinamis (Selaras dengan Target Labeler)
                is_valid_buy = (low_vals <= (lwma_low_zone + buffer_zone)) if lwma_low_zone is not None else np.ones(len(df_test), dtype=bool)
                is_valid_sell = (high_vals >= (lwma_high_zone - buffer_zone)) if lwma_high_zone is not None else np.ones(len(df_test), dtype=bool)

                preds = np.zeros(len(df_test), dtype=int)
                if is_binary:
                    idx_w = classes.index(1) if 1 in classes else 1
                    p_win = probs[:, idx_w] if probs.shape[1] > idx_w else probs[:, -1]
                    preds[(p_win >= entry_thresh) & is_valid_buy] = 1
                    preds[(p_win >= entry_thresh) & is_valid_sell] = 2
                else:
                    idx_buy = classes.index(1) if 1 in classes else -1
                    idx_sell = classes.index(2) if 2 in classes else -1
                    p_buy = probs[:, idx_buy] if idx_buy != -1 else np.zeros(len(df_test))
                    p_sell = probs[:, idx_sell] if idx_sell != -1 else np.zeros(len(df_test))
                    preds[(p_buy >= entry_thresh) & (p_buy > p_sell) & is_valid_buy] = 1
                    preds[(p_sell >= entry_thresh) & (p_sell > p_buy) & is_valid_sell] = 2
            else:
                preds = model.predict(X_test)
            
            all_y_true.extend(y_test.tolist())
            all_y_pred.extend(preds.tolist())
            test_chunk_idx += 1
            
        if not all_y_true:
            logging.warning(f"Tidak ada data validasi OOS untuk mode {mode}.")
            return 0.0
            
        y_true_arr = np.array(all_y_true)
        y_pred_arr = np.array(all_y_pred)
        
        # 1. Global Raw Accuracy
        raw_accuracy = float((y_pred_arr == y_true_arr).mean())
        
        # 2. Institutional Trading Metrics (Hanya candle di mana model memutuskan masuk pasar: Buy=1 atau Sell=2)
        trade_mask = (y_pred_arr == 1) | (y_pred_arr == 2)
        total_signals = int(trade_mask.sum())
        
        if total_signals > 0:
            is_legacy_multiclass = 2 in y_true_arr
            if is_legacy_multiclass:
                trades_correct = int(((y_pred_arr == 1) & (y_true_arr == 1)).sum() + ((y_pred_arr == 2) & (y_true_arr == 2)).sum())
            else:
                trades_correct = int((y_true_arr[trade_mask] == 1).sum())

            trade_win_rate = trades_correct / total_signals
            trades_lost = total_signals - trades_correct
            
            # Precision per class
            buy_mask = y_pred_arr == 1
            sell_mask = y_pred_arr == 2
            precision_buy = float((y_true_arr[buy_mask] == 1).mean()) if buy_mask.sum() > 0 else 0.0
            if is_legacy_multiclass:
                precision_sell = float((y_true_arr[sell_mask] == 2).mean()) if sell_mask.sum() > 0 else 0.0
            else:
                precision_sell = float((y_true_arr[sell_mask] == 1).mean()) if sell_mask.sum() > 0 else 0.0
            
            # Asumsi Reward-to-Risk ratio: Normal mode 1:2.0 (sesuai target_labeler), Runner mode 1:5.0
            rr_ratio = 2.0 if mode == 'normal' else getattr(self.researcher, 'max_runner_rr', 5.0)
            gross_profit = trades_correct * rr_ratio
            gross_loss = max(trades_lost * 1.0, 0.001)
            profit_factor = gross_profit / gross_loss
            expectancy = (trade_win_rate * rr_ratio) - ((1.0 - trade_win_rate) * 1.0)
        else:
            trades_correct = 0
            trade_win_rate = 0.0
            precision_buy = 0.0
            precision_sell = 0.0
            profit_factor = 0.0
            expectancy = 0.0
            
        # Catat metrik institusional lengkap
        metrics = {
            "mode": mode,
            "raw_accuracy": round(raw_accuracy * 100, 2),
            "trade_signals": total_signals,
            "trade_win_rate": round(trade_win_rate * 100, 2),
            "precision_buy": round(precision_buy * 100, 2),
            "precision_sell": round(precision_sell * 100, 2),
            "profit_factor": round(profit_factor, 2),
            "expectancy": round(expectancy, 3),
        }
        self.last_metrics[mode] = metrics
        
        logging.info(
            f"📊 [OOS EVALUATION - {mode.upper()}] "
            f"Raw Acc: {metrics['raw_accuracy']}% | Signals: {total_signals} | "
            f"Win Rate: {metrics['trade_win_rate']}% | Buy Prec: {metrics['precision_buy']}% | "
            f"Sell Prec: {metrics['precision_sell']}% | Profit Factor: {metrics['profit_factor']} | "
            f"Expectancy: {metrics['expectancy']:+.2f}R"
        )
        
        # Skor akhir validasi: MURNI TRADE WIN RATE (Tanpa modifikasi matematika)
        # Kelulusan model mengacu langsung pada Trade Win Rate riil di atas batas 50% (Normal) atau 25% (Runner)
        # Menolak kelulusan semu jika sinyal terlalu sedikit (tidak memenuhi statistical significance)
        min_required_signals = 10 if mode == 'runner' else 15
        if total_signals >= min_required_signals:
            return float(trade_win_rate)
        elif mode == 'runner' and total_signals >= 5 and trade_win_rate >= 0.25 and profit_factor >= 1.5:
            logging.info(f"✅ Runner Mode OOS lolos dengan sinyal selektif ({total_signals} sinyal, WR: {trade_win_rate*100:.1f}%, PF: {profit_factor:.2f}, Exp: {expectancy:+.2f}R).")
            return float(trade_win_rate)
        else:
            logging.warning(f"❌ Validasi GAGAL: Jumlah sinyal validasi terlalu sedikit ({total_signals} sinyal < {min_required_signals} sinyal minimum). Model tidak memenuhi syarat statistical significance.")
            return 0.0
            
        return float(raw_accuracy)
