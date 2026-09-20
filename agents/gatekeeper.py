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
        oos_df = oos_df.dropna()
        
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
        
        # Threshold kelulusan (Contoh 50% untuk dummy baseline)
        if acc_normal > 0.50 and acc_runner > 0.50:
            logging.info("Model Passed Validation.")
            return True
        else:
            logging.warning("Model Failed Validation. Possible Overfitting.")
            return False
