import logging
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import numpy as np
import pandas as pd
import os
import joblib

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
        
    def save_models(self):
        try:
            os.makedirs("models", exist_ok=True)
            if self.model_normal is not None:
                joblib.dump(self.model_normal, "models/model_normal.pkl")
            if self.model_runner is not None:
                joblib.dump(self.model_runner, "models/model_runner.pkl")
            logging.info("Model checkpoints saved to 'models/' directory.")
        except Exception as e:
            logging.error(f"Failed to save models: {e}")

    def load_models(self):
        try:
            if os.path.exists("models/model_normal.pkl") and os.path.exists("models/model_runner.pkl"):
                self.model_normal = joblib.load("models/model_normal.pkl")
                self.model_runner = joblib.load("models/model_runner.pkl")
                
                if hasattr(self.model_normal, 'feature_name_'):
                    self.features = list(self.model_normal.feature_name_)
                elif hasattr(self.model_normal, 'booster_'):
                    self.features = self.model_normal.booster_.feature_name()
                
                logging.info("Model checkpoints loaded successfully.")
                return True
        except Exception as e:
            logging.error(f"Failed to load models: {e}")
        return False
        
    def generate_targets(self, df):
        logging.info("Generating dynamic ATR-based targets...")
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

    def optimize_hyperparameters(self, X, y, sample_weights, n_trials=20):
        import optuna
        from sklearn.metrics import accuracy_score
        
        # Split subset of data for fast evaluation
        X_train, X_val, y_train, y_val, sw_train, sw_val = train_test_split(
            X, y, sample_weights, test_size=0.2, shuffle=False
        )

        def objective(trial):
            params = {
                'n_estimators': trial.suggest_int('n_estimators', 50, 150),
                'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1, log=True),
                'max_depth': trial.suggest_int('max_depth', 3, 7),
                'num_leaves': trial.suggest_int('num_leaves', 10, 31),
                'min_child_samples': trial.suggest_int('min_child_samples', 20, 100),
                'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                'random_state': 42,
                'verbose': -1
            }
            
            model = lgb.LGBMClassifier(**params)
            model.fit(X_train, y_train, sample_weight=sw_train)
            preds = model.predict(X_val)
            acc = accuracy_score(y_val, preds)
            return acc
            
        study = optuna.create_study(direction='maximize')
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study.optimize(objective, n_trials=n_trials)
        
        return study.best_params

    def train_models(self, data_generator, total_chunks=1, progress_callback=None):
        import gc
        logging.info("Training LightGBM Dual-Target models with RLHF & PnL Feedback (Optuna Auto-Tuning)...")
        
        self.model_normal = None
        self.model_runner = None
        
        best_params_normal = None
        best_params_runner = None
        
        try:
            from database import get_approved_setup_ids, get_historical_pnl_feedback
            approved_ids = get_approved_setup_ids()
            pnl_df = get_historical_pnl_feedback()
        except Exception as e:
            logging.warning(f"[PnL Feedback] Tidak dapat memuat data historis: {e}")
            approved_ids = []
            pnl_df = pd.DataFrame()

        chunk_idx = 1
        for df in data_generator:
            if df.empty:
                continue
                
            df = self.generate_targets(df)
            df = df.dropna()
            
            if df.empty:
                continue
                
            # Features (excluding target columns and absolute prices to prevent memorization/100% prob)
            forbidden_exact = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            forbidden_cols = []
            for tf in ['', '_m5', '_m15']:
                for c in forbidden_exact:
                    forbidden_cols.append(f"{c}{tf}")
                for c in ['SMA_20', 'BB_Upper', 'BB_Lower', 'EMA_50', 'LWMA_5_High', 'LWMA_10_High', 'LWMA_5_Low', 'LWMA_10_Low']:
                    forbidden_cols.append(f"{c}{tf}")

            self.features = [col for col in df.columns if col not in forbidden_cols and 'Target' not in col]
            X = df[self.features]
            
            logging.info(f"Chunk {chunk_idx}/{total_chunks}: Extracting {len(self.features)} features for training.")
            
            y_normal = df['Target_Normal']
            y_runner = df['Target_Runner']
            
            # RLHF
            sample_weights = np.ones(len(df), dtype=float)
            if approved_ids:
                matched_count = 0
                for i in range(len(df)):
                    row_id_str = str(df.index[i])
                    row_time_str = df.index[i].strftime("%Y-%m-%d %H:%M:%S") if hasattr(df.index[i], "strftime") else row_id_str
                    if row_id_str in approved_ids or row_time_str in approved_ids:
                        sample_weights[i] = 5.0
                        matched_count += 1
                if matched_count > 0:
                    logging.info(f"[RLHF] Ditemukan {matched_count} setup Approve di chunk {chunk_idx}.")

            # PnL Feedback Loop (Real Live Trade Loss = Penalty, Profit = Reward)
            if not pnl_df.empty:
                time_col = df['time'] if 'time' in df.columns else df.index
                df_time_floor = pd.to_datetime(time_col).dt.floor('Min')
                pnl_time_floor = pnl_df['time'].dt.floor('Min')
                
                matched_pnl = 0
                for pnl_idx, pnl_row in pnl_df.iterrows():
                    match_idx = np.where(df_time_floor == pnl_time_floor[pnl_idx])[0]
                    if len(match_idx) > 0:
                        idx = match_idx[0]
                        if pnl_row['profit'] < 0:
                            sample_weights[idx] = 0.5 # Penalti ringan (bukan 0.1) agar model tetap memperhitungkan kondisi pasar
                        elif pnl_row['profit'] > 0:
                            sample_weights[idx] = 1.5 # Reward diseimbangkan menjadi 1.5
                        matched_pnl += 1
                if matched_pnl > 0:
                    logging.info(f"[PnL Feedback] Diterapkan pada {matched_pnl} eksekusi dari riwayat live.")

            # Optuna Auto-Tuning di Chunk Pertama
            if chunk_idx == 1 and len(X) > 100:
                logging.info(f"Chunk {chunk_idx}: Menjalankan Optuna Auto-Tuning untuk 20 iterasi...")
                best_params_normal = self.optimize_hyperparameters(X, y_normal, sample_weights, n_trials=20)
                best_params_runner = self.optimize_hyperparameters(X, y_runner, sample_weights, n_trials=20)
                logging.info(f"[Optuna] Parameter Terbaik Normal: {best_params_normal}")
                logging.info(f"[Optuna] Parameter Terbaik Runner: {best_params_runner}")
                
            params_n = best_params_normal if best_params_normal else {
                'n_estimators': 100, 'learning_rate': 0.05, 'max_depth': 4, 'num_leaves': 15,
                'min_child_samples': 50, 'subsample': 0.8, 'colsample_bytree': 0.8, 'random_state': 42
            }
            params_r = best_params_runner if best_params_runner else params_n
            
            # Tambahkan verbose = -1 agar tidak berisik
            params_n['verbose'] = -1
            params_r['verbose'] = -1

            # Train Normal Model
            if self.model_normal is None:
                self.model_normal = lgb.LGBMClassifier(**params_n)
                self.model_normal.fit(X, y_normal, sample_weight=sample_weights)
            else:
                self.model_normal.fit(X, y_normal, sample_weight=sample_weights, init_model=self.model_normal)
                
            # Train Runner Model
            if self.model_runner is None:
                self.model_runner = lgb.LGBMClassifier(**params_r)
                self.model_runner.fit(X, y_runner, sample_weight=sample_weights)
            else:
                self.model_runner.fit(X, y_runner, sample_weight=sample_weights, init_model=self.model_runner)
                
            logging.info(f"Chunk {chunk_idx}/{total_chunks} processed.")
            
            if progress_callback:
                progress_callback(chunk_idx, total_chunks)
                
            chunk_idx += 1
            
            # Garbage Collection
            del df, X, y_normal, y_runner, sample_weights
            gc.collect()
            
        logging.info("Models trained successfully with RLHF weights (Incremental).")
        
        # Log Top 10 Feature Importances
        if hasattr(self.model_normal, 'feature_importances_') and self.features:
            try:
                importances = self.model_normal.feature_importances_
                top_indices = np.argsort(importances)[-10:][::-1]
                logging.info("=== TOP 10 FEATURE IMPORTANCES ===")
                for rank, idx in enumerate(top_indices, 1):
                    feat_name = self.features[idx]
                    feat_imp = importances[idx]
                    logging.info(f"{rank}. {feat_name}: {feat_imp}")
                logging.info("==================================")
            except Exception as e:
                logging.debug(f"Failed to log feature importances: {e}")
                
        self.save_models()
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

    def get_live_probabilities(self, X_live):
        """
        Membaca skor probabilitas seketika (live) dari model yang telah dilatih
        (Digunakan untuk pemicu Dynamic Exhaustion Exit).
        """
        if self.model_normal is None or self.model_runner is None:
            return {"normal": 0.5, "runner": 0.5}

        # Filter kolom fitur yang valid
        if isinstance(X_live, pd.Series):
            X_live = pd.DataFrame([X_live])
            
        valid_cols = [c for c in self.features if c in X_live.columns]
        if not valid_cols:
            return {"normal": 0.5, "runner": 0.5}

        try:
            X_eval = X_live[valid_cols]
            prob_normal = self.model_normal.predict_proba(X_eval)[0, 1]
            prob_runner = self.model_runner.predict_proba(X_eval)[0, 1]
            return {"normal": float(prob_normal), "runner": float(prob_runner)}
        except Exception as e:
            logging.debug(f"Gagal kalkulasi live probabilities: {e}")
            return {"normal": 0.5, "runner": 0.5}
