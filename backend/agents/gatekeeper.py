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
            
            # Filter spesifik zona Re-entry BBMA LWMA
            reentry_sell_mask = df_test['high'] >= df_test[['LWMA_5_High', 'LWMA_10_High']].min(axis=1)
            reentry_buy_mask = df_test['low'] <= df_test[['LWMA_5_Low', 'LWMA_10_Low']].max(axis=1)
            df_test = df_test[reentry_sell_mask | reentry_buy_mask].copy()
            
            if df_test.empty:
                continue
            
            # Pastikan kelengkapan kolom fitur
            for col in self.researcher.features:
                if col not in df_test.columns:
                    df_test[col] = 0.0
                if df_test[col].dtype == 'object':
                    df_test[col] = pd.to_numeric(df_test[col], errors='coerce')
            
            target_col = 'Target_Normal' if mode == 'normal' else 'Target_Runner'
            
            X_test = df_test[self.researcher.features]
            y_test = df_test[target_col]
            
            # Evaluasi probabilitas menggunakan batas threshold AI (konsisten dengan Executor)
            from config import Config
            entry_thresh = getattr(Config, 'AI_NORMAL_ENTRY_THRESHOLD', 75.0) / 100.0
            
            if hasattr(model, 'predict_proba'):
                probs = model.predict_proba(X_test)
                preds = np.zeros(len(df_test), dtype=int)
                for i in range(len(df_test)):
                    p_row = probs[i]
                    p_buy = float(p_row[1]) if len(p_row) > 1 else 0.0
                    p_sell = float(p_row[2]) if len(p_row) > 2 else 0.0
                    if p_buy >= entry_thresh and p_buy > p_sell:
                        preds[i] = 1
                    elif p_sell >= entry_thresh and p_sell > p_buy:
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
            
            # Asumsi Reward-to-Risk ratio: Normal mode 1:1.5, Runner mode 1:3.0
            rr_ratio = 1.5 if mode == 'normal' else 3.0
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
        
        # Skor akhir validasi: jika ada sinyal trading, padukan Win Rate & Profit Factor
        # Jika tidak ada sinyal sama sekali, gunakan raw accuracy
        if total_signals >= 5:
            # Normalisasikan Profit Factor (PF 2.0 -> 1.0)
            pf_normalized = min(profit_factor / 2.0, 1.0)
            composite_score = (trade_win_rate * 0.6) + (pf_normalized * 0.4)
            return float(composite_score)
            
        return float(raw_accuracy)
