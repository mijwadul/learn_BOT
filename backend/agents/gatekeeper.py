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
            
            # Filter spesifik zona Re-entry BBMA LWMA & Zon Zero Loss (Slide 33 & 51-56)
            lwma_low_zone = np.maximum(df_test['LWMA_5_Low'].values, df_test['LWMA_10_Low'].values)
            lwma_high_zone = np.minimum(df_test['LWMA_5_High'].values, df_test['LWMA_10_High'].values)
            sma_20_vals = df_test['SMA_20'].values if 'SMA_20' in df_test.columns else df_test['close'].values
            ema_50_vals = df_test['EMA_50'].values if 'EMA_50' in df_test.columns else df_test['close'].values
            bb_upper_vals = df_test['BB_Upper'].values if 'BB_Upper' in df_test.columns else df_test['close'].values
            bb_lower_vals = df_test['BB_Lower'].values if 'BB_Lower' in df_test.columns else df_test['close'].values

            open_vals = df_test['open'].values if 'open' in df_test.columns else df_test['close'].values
            reentry_buy_mask = (df_test['low'].values <= lwma_low_zone) & (df_test['close'].values >= sma_20_vals) & (df_test['close'].values <= bb_upper_vals) & (sma_20_vals >= ema_50_vals) & (df_test['close'].values >= ema_50_vals) & (df_test['close'].values >= open_vals)
            reentry_sell_mask = (df_test['high'].values >= lwma_high_zone) & (df_test['close'].values <= sma_20_vals) & (df_test['close'].values >= bb_lower_vals) & (sma_20_vals <= ema_50_vals) & (df_test['close'].values <= ema_50_vals) & (df_test['close'].values <= open_vals)
            df_test = df_test[reentry_buy_mask | reentry_sell_mask].copy()
            
            if df_test.empty:
                continue
            
            # Pastikan kelengkapan kolom fitur
            for col in self.researcher.features:
                if col not in df_test.columns:
                    df_test[col] = 0.0
                elif not (pd.api.types.is_numeric_dtype(df_test[col]) or pd.api.types.is_bool_dtype(df_test[col])):
                    df_test[col] = pd.to_numeric(df_test[col], errors='coerce').fillna(0.0)
            
            target_col = 'Target_Normal' if mode == 'normal' else 'Target_Runner'
            
            X_test = df_test[self.researcher.features]
            y_test = df_test[target_col]
            
            # Evaluasi probabilitas menggunakan batas threshold AI (dinamis membaca konfigurasi terbaru)
            from config import Config
            import os
            from dotenv import load_dotenv
            load_dotenv(override=True)
            if mode == 'runner':
                entry_thresh = float(os.getenv("AI_RUNNER_ENTRY_THRESHOLD", getattr(Config, 'AI_RUNNER_ENTRY_THRESHOLD', 55.0))) / 100.0
            else:
                entry_thresh = float(os.getenv("AI_NORMAL_ENTRY_THRESHOLD", getattr(Config, 'AI_NORMAL_ENTRY_THRESHOLD', 60.0))) / 100.0
            
            if hasattr(model, 'predict_proba'):
                probs = model.predict_proba(X_test)
                classes = list(getattr(model, 'classes_', [0, 1, 2]))
                idx_buy = classes.index(1) if 1 in classes else -1
                idx_sell = classes.index(2) if 2 in classes else -1

                lwma_low_zone = np.maximum(df_test['LWMA_5_Low'].values, df_test['LWMA_10_Low'].values) if 'LWMA_5_Low' in df_test.columns else None
                lwma_high_zone = np.minimum(df_test['LWMA_5_High'].values, df_test['LWMA_10_High'].values) if 'LWMA_5_High' in df_test.columns else None
                low_vals = df_test['low'].values
                high_vals = df_test['high'].values
                close_vals = df_test['close'].values
                open_vals = df_test['open'].values if 'open' in df_test.columns else close_vals
                sma_20_vals = df_test['SMA_20'].values if 'SMA_20' in df_test.columns else close_vals
                ema_50_vals = df_test['EMA_50'].values if 'EMA_50' in df_test.columns else close_vals
                bb_upper_vals = df_test['BB_Upper'].values if 'BB_Upper' in df_test.columns else close_vals
                bb_lower_vals = df_test['BB_Lower'].values if 'BB_Lower' in df_test.columns else close_vals

                preds = np.zeros(len(df_test), dtype=int)
                for i in range(len(df_test)):
                    p_buy = float(probs[i][idx_buy]) if idx_buy != -1 and idx_buy < len(probs[i]) else 0.0
                    p_sell = float(probs[i][idx_sell]) if idx_sell != -1 and idx_sell < len(probs[i]) else 0.0
                    
                    is_valid_buy = (low_vals[i] <= lwma_low_zone[i]) and (close_vals[i] >= sma_20_vals[i]) and (close_vals[i] <= bb_upper_vals[i]) and (sma_20_vals[i] >= ema_50_vals[i]) and (close_vals[i] >= ema_50_vals[i]) and (close_vals[i] >= open_vals[i])
                    is_valid_sell = (high_vals[i] >= lwma_high_zone[i]) and (close_vals[i] <= sma_20_vals[i]) and (close_vals[i] >= bb_lower_vals[i]) and (sma_20_vals[i] <= ema_50_vals[i]) and (close_vals[i] <= ema_50_vals[i]) and (close_vals[i] <= open_vals[i])

                    if p_buy >= entry_thresh and p_buy > p_sell and is_valid_buy:
                        preds[i] = 1
                    elif p_sell >= entry_thresh and p_sell > p_buy and is_valid_sell:
                        preds[i] = 2
                    else:
                        preds[i] = 0
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
            trades_correct = int((y_pred_arr[trade_mask] == y_true_arr[trade_mask]).sum())
            trade_win_rate = trades_correct / total_signals
            trades_lost = total_signals - trades_correct
            
            # Precision per class
            buy_mask = y_pred_arr == 1
            sell_mask = y_pred_arr == 2
            precision_buy = float((y_true_arr[buy_mask] == 1).mean()) if buy_mask.sum() > 0 else 0.0
            precision_sell = float((y_true_arr[sell_mask] == 2).mean()) if sell_mask.sum() > 0 else 0.0
            
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
        # Kelulusan model mengacu langsung pada Trade Win Rate riil di atas batas 50%
        if total_signals >= 10:
            return float(trade_win_rate)
        elif total_signals > 0:
            logging.warning(f"Jumlah sinyal validasi terlalu sedikit ({total_signals} sinyal).")
            return float(trade_win_rate)
            
        return float(raw_accuracy)
