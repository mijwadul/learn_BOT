import logging
from sklearn.metrics import accuracy_score

logging.basicConfig(level=logging.INFO)

class GatekeeperAgent:
    """
    Agent 3: The Gatekeeper (Out-of-Sample Validator)
    Menolak model yang overfitting melalui Walk-Forward Backtest.
    """
    
    def __init__(self, researcher_agent):
        self.researcher = researcher_agent

    def validate_model(self, oos_df):
        logging.info("Validating models on Out-of-Sample data...")
        
        if self.researcher.model_normal is None or self.researcher.model_runner is None:
            logging.error("Models have not been trained yet.")
            return False
            
        # Ensure targets are generated on OOS data
        oos_df = self.researcher.generate_targets(oos_df.copy())
        
        if oos_df.empty:
            logging.error("OOS Data is empty after target generation.")
            return False
            
        X_oos = oos_df[self.researcher.features]
        y_normal_oos = oos_df['Target_Normal']
        y_runner_oos = oos_df['Target_Runner']
        
        # Predict
        pred_normal = self.researcher.model_normal.predict(X_oos)
        pred_runner = self.researcher.model_runner.predict(X_oos)
        
        # Simple validation metric
        acc_normal = accuracy_score(y_normal_oos, pred_normal)
        acc_runner = accuracy_score(y_runner_oos, pred_runner)
        
        logging.info(f"OOS Accuracy - Normal: {acc_normal:.2f} (Threshold: >0.50)")
        logging.info(f"OOS Accuracy - Runner: {acc_runner:.2f} (Threshold: >0.50)")
        
        from database import bulk_add_hard_negatives
        
        hn_records = []
        
        # Ekstrak kesalahan (Hard Negatives)
        for i in range(len(oos_df)):
            idx_time = oos_df.index[i]
            row_time_str = idx_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx_time, "strftime") else str(idx_time)
            
            if pred_normal[i] != y_normal_oos.iloc[i]:
                hn_records.append({'setup_id': row_time_str, 'failed_mode': 'Normal'})
            if pred_runner[i] != y_runner_oos.iloc[i]:
                hn_records.append({'setup_id': row_time_str, 'failed_mode': 'Runner'})
                
        misclassified_count = len(hn_records)
        if misclassified_count > 0:
            inserted = bulk_add_hard_negatives(hn_records)
            logging.info(f"Berhasil menyimpan {inserted} baris Hard Negatives baru ke database (dari {misclassified_count} total kesalahan).")
        
        # Threshold kelulusan (Contoh 50% untuk dummy baseline)
        passed_normal = acc_normal > 0.50
        passed_runner = acc_runner > 0.50
        passed = passed_normal and passed_runner
        
        if passed:
            logging.info("Model Passed Validation.")
        else:
            logging.warning(f"Model Failed Validation. Logged {misclassified_count} Hard Negatives.")
            
        return passed_normal, passed_runner, misclassified_count
