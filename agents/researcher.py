import logging
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)

class ResearcherAgent:
    """
    Agent 2: The Researcher (Dual-Target AI Brain)
    Melatih algoritma (LightGBM) menggunakan target dinamis.
    """
    
    def __init__(self):
        self.model_normal = None
        self.model_runner = None
        self.features = []
        
    def generate_targets(self, df):
        from utils.indicators import calculate_atr
        df['ATR_14'] = calculate_atr(df, 14)
        
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        atrs = df['ATR_14'].values
        
        n = len(df)
        labels_normal = np.zeros(n)
        labels_runner = np.zeros(n)
        
        # Dynamic ATR-based Target Generation
        for i in range(n):
            if np.isnan(atrs[i]):
                continue
                
            entry_price = closes[i]
            sl_dist = atrs[i]
            
            # Target_Normal: RR 1:2 (Hit & Run), lookahead hingga 100 candle
            tp_normal_level = entry_price + (sl_dist * 2.0)
            sl_normal_level = entry_price - sl_dist
            
            for j in range(i + 1, min(i + 101, n)):
                if lows[j] <= sl_normal_level:
                    labels_normal[i] = 0
                    break
                if highs[j] >= tp_normal_level:
                    labels_normal[i] = 1
                    break

            # Target_Runner: Dinamis menggunakan ATR_14 (TP = 5x jarak SL, lookahead pemindaian hingga 300 candle)
            tp_runner_level = entry_price + (sl_dist * 5.0)
            sl_runner_level = entry_price - sl_dist
            
            for j in range(i + 1, min(i + 301, n)):
                if lows[j] <= sl_runner_level:
                    labels_runner[i] = 0
                    break
                if highs[j] >= tp_runner_level:
                    labels_runner[i] = 1
                    break
                    
        df['Target_Normal'] = labels_normal
        df['Target_Runner'] = labels_runner
        
        # Simpan fitur ATR_14 untuk analisis volatilitas di model
        return df

    def train_models(self, df):
        logging.info("Training LightGBM Dual-Target models with RLHF Sample Weighting...")
        df = self.generate_targets(df)
        df = df.dropna()
        
        # Features (excluding target columns)
        self.features = [col for col in df.columns if 'Target' not in col]
        X = df[self.features]
        
        y_normal = df['Target_Normal']
        y_runner = df['Target_Runner']
        
        # RLHF (Human-in-the-Loop): Berikan sample weights lebih tinggi pada data yang sudah di-Approve
        sample_weights = np.ones(len(df), dtype=float)
        try:
            from database import get_approved_setup_ids
            approved_ids = get_approved_setup_ids()
            if approved_ids:
                matched_count = 0
                for i in range(len(df)):
                    # Format index sebagai string untuk dicocokkan dengan ID setup
                    row_id_str = str(df.index[i])
                    row_time_str = df.index[i].strftime("%Y-%m-%d %H:%M:%S") if hasattr(df.index[i], "strftime") else row_id_str
                    if row_id_str in approved_ids or row_time_str in approved_ids:
                        sample_weights[i] = 5.0 # Bobot 5.0x untuk setup yang disetujui manusia
                        matched_count += 1
                logging.info(f"[RLHF] Ditemukan {matched_count} setup yang telah di-Approve. Diberi bobot prioritas 5.0x.")
        except Exception as e:
            logging.warning(f"[RLHF] Tidak dapat memuat approved_setups untuk weighting: {e}")

        # Train Normal Model (dengan sample_weight RLHF)
        self.model_normal = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, random_state=42)
        self.model_normal.fit(X, y_normal, sample_weight=sample_weights)
        
        # Train Runner Model (dengan sample_weight RLHF)
        self.model_runner = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, random_state=42)
        self.model_runner.fit(X, y_runner, sample_weight=sample_weights)
        
        logging.info("Models trained successfully with RLHF weights.")
        return True

    def get_top_feature_contributions(self, X_row, top_n=3):
        """
        XAI (Explainable AI):
        Mengekstrak Top 3 Feature Contributions dari model LightGBM untuk keputusan eksekusi.
        """
        if self.model_normal is None:
            return "Sinyal Breakout Topografi BBMA & ATR"

        try:
            # Jika X_row adalah Series atau dict, ubah ke DataFrame
            if isinstance(X_row, pd.Series):
                X_row = pd.DataFrame([X_row])
                
            # Filter kolom fitur yang valid
            valid_cols = [c for c in self.features if c in X_row.columns]
            if not valid_cols:
                return "Sinyal Topografi BBMA & ATR"
                
            X_eval = X_row[valid_cols]
            
            # Ekstrak SHAP feature contributions langsung dari LightGBM Booster
            if hasattr(self.model_normal, 'booster_'):
                contribs = self.model_normal.booster_.predict(X_eval, pred_contrib=True)[0]
                feat_contribs = list(zip(valid_cols, contribs[:-1]))
                top_features = sorted(feat_contribs, key=lambda x: abs(x[1]), reverse=True)[:top_n]
                
                parts = []
                for feat, val in top_features:
                    sign = "+" if val >= 0 else ""
                    parts.append(f"{feat} ({sign}{val:.2f})")
                return "Top 3 Fitur: " + ", ".join(parts)
        except Exception as e:
            logging.debug(f"Gagal kalkulasi feature contribution SHAP: {e}")

        # Fallback ke feature importances global
        try:
            if hasattr(self.model_normal, 'feature_importances_'):
                top_idx = np.argsort(self.model_normal.feature_importances_)[-top_n:][::-1]
                top_f = [self.features[i] for i in top_idx]
                return "Top 3 Fitur Utama: " + ", ".join(top_f)
        except Exception:
            pass

        return "BBMA Convergence & Momentum ATR"
