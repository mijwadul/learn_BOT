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
        
        # Menambahkan EMA_50 untuk mendeteksi tren/posisi trading
        from utils.indicators import calculate_ema
        if 'EMA_50' not in df.columns:
            df['EMA_50'] = calculate_ema(df['close'], 50)
            
        if 'dist_Close_EMA50' not in df.columns:
            df['dist_Close_EMA50'] = df['close'] - df['EMA_50']
            
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
            tp_buy_normal = entry_price + (sl_dist * 2.0)
            sl_buy_normal = entry_price - sl_dist
            tp_sell_normal = entry_price - (sl_dist * 2.0)
            sl_sell_normal = entry_price + sl_dist
            
            buy_success = False
            buy_failed = False
            sell_success = False
            sell_failed = False
            
            for j in range(i + 1, min(i + 101, n)):
                if not buy_failed and not buy_success:
                    if lows[j] <= sl_buy_normal:
                        buy_failed = True
                    elif highs[j] >= tp_buy_normal:
                        buy_success = True
                        
                if not sell_failed and not sell_success:
                    if highs[j] >= sl_sell_normal:
                        sell_failed = True
                    elif lows[j] <= tp_sell_normal:
                        sell_success = True
                        
                if (buy_success or buy_failed) and (sell_success or sell_failed):
                    break
                    
            if buy_success and not sell_success:
                labels_normal[i] = 1
            elif sell_success and not buy_success:
                labels_normal[i] = 2
            else:
                labels_normal[i] = 0

            # Target_Runner: Dinamis menggunakan ATR_14 (TP = 5x jarak SL, lookahead pemindaian hingga 300 candle)
            tp_buy_runner = entry_price + (sl_dist * 5.0)
            sl_buy_runner = entry_price - sl_dist
            tp_sell_runner = entry_price - (sl_dist * 5.0)
            sl_sell_runner = entry_price + sl_dist
            
            buy_success_runner = False
            buy_failed_runner = False
            sell_success_runner = False
            sell_failed_runner = False
            
            for j in range(i + 1, min(i + 301, n)):
                if not buy_failed_runner and not buy_success_runner:
                    if lows[j] <= sl_buy_runner:
                        buy_failed_runner = True
                    elif highs[j] >= tp_buy_runner:
                        buy_success_runner = True
                        
                if not sell_failed_runner and not sell_success_runner:
                    if highs[j] >= sl_sell_runner:
                        sell_failed_runner = True
                    elif lows[j] <= tp_sell_runner:
                        sell_success_runner = True
                        
                if (buy_success_runner or buy_failed_runner) and (sell_success_runner or sell_failed_runner):
                    break
                    
            if buy_success_runner and not sell_success_runner:
                labels_runner[i] = 1
            elif sell_success_runner and not buy_success_runner:
                labels_runner[i] = 2
            else:
                labels_runner[i] = 0
                        
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

    def _fetch_rlhf_pnl_data(self):
        try:
            from database import get_approved_setup_ids, get_rejected_setup_ids, get_historical_pnl_feedback, get_hard_negative_ids
            approved_ids = set(get_approved_setup_ids())
            rejected_ids = set(get_rejected_setup_ids())
            hard_negative_ids = set(get_hard_negative_ids())
            pnl_df = get_historical_pnl_feedback()
        except Exception as e:
            logging.error(f"Failed to fetch RLHF/PnL data: {e}")
            approved_ids, rejected_ids, hard_negative_ids = set(), set(), set()
            pnl_df = pd.DataFrame()
        return approved_ids, rejected_ids, hard_negative_ids, pnl_df

    def train_normal_mode(self, data_generator, total_chunks=1, progress_callback=None):
        import gc
        logging.info("Training LightGBM Normal Mode (Scalping) with RLHF & PnL Feedback (Optuna Auto-Tuning).")
        
        best_params_normal = None
        approved_ids, rejected_ids, hard_negative_ids, pnl_df = self._fetch_rlhf_pnl_data()

        chunk_idx = 1
        for df in data_generator:
            if df.empty:
                continue
                
            df = self.generate_targets(df)
            reentry_sell_mask = df['high'] >= df[['LWMA_5_High', 'LWMA_10_High']].min(axis=1)
            reentry_buy_mask = df['low'] <= df[['LWMA_5_Low', 'LWMA_10_Low']].max(axis=1)
            df = df[reentry_sell_mask | reentry_buy_mask].copy()

            if df.empty or len(df) < 50:
                continue
                
            forbidden_exact = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            forbidden_cols = []
            # Isolasi Dataset: Normal Mode tidak memuat fitur kompleks H4 untuk menghemat memori drastis
            for tf in ['', '_m5', '_m15', '_h1']:
                for c in forbidden_exact:
                    forbidden_cols.append(f"{c}{tf}")
                for c in ['SMA_20', 'BB_Upper', 'BB_Lower', 'EMA_50', 'LWMA_5_High', 'LWMA_10_High', 'LWMA_5_Low', 'LWMA_10_Low']:
                    forbidden_cols.append(f"{c}{tf}")

            self.features = [col for col in df.columns if col not in forbidden_cols and 'Target' not in col and not col.endswith('_h4')]
            
            for col in self.features:
                if df[col].dtype == 'object':
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    
            X = df[self.features]
            y_normal = df['Target_Normal']
            
            sample_weights = np.ones(len(df), dtype=float)
            if approved_ids or rejected_ids or hard_negative_ids:
                for i in range(len(df)):
                    row_id_str = str(df.index[i])
                    row_time_str = df.index[i].strftime("%Y-%m-%d %H:%M:%S") if hasattr(df.index[i], "strftime") else row_id_str
                    if row_id_str in hard_negative_ids or row_time_str in hard_negative_ids:
                        sample_weights[i] = 3.0
                    elif row_id_str in approved_ids or row_time_str in approved_ids:
                        sample_weights[i] = 5.0
                    elif row_id_str in rejected_ids or row_time_str in rejected_ids:
                        sample_weights[i] = 0.1

            if not pnl_df.empty:
                if 'time' in df.columns:
                    df_time_floor = pd.to_datetime(df['time']).dt.floor('Min')
                else:
                    df_time_floor = pd.to_datetime(df.index).floor('Min')
                pnl_time_floor = pnl_df['time'].dt.floor('Min')
                for pnl_idx, pnl_row in pnl_df.iterrows():
                    match_idx = np.where(df_time_floor == pnl_time_floor[pnl_idx])[0]
                    if len(match_idx) > 0:
                        idx = match_idx[0]
                        if pnl_row['profit'] < 0:
                            sample_weights[idx] = 0.5
                        elif pnl_row['profit'] > 0:
                            sample_weights[idx] = 1.5

            if chunk_idx == 1 and len(X) > 100:
                best_params_normal = self.optimize_hyperparameters(X, y_normal, sample_weights, n_trials=20)
                
            params_n = best_params_normal if best_params_normal else {
                'n_estimators': 100, 'learning_rate': 0.05, 'max_depth': 4, 'num_leaves': 15,
                'min_child_samples': 50, 'subsample': 0.8, 'colsample_bytree': 0.8, 'random_state': 42
            }
            params_n['verbose'] = -1

            if self.model_normal is None:
                self.model_normal = lgb.LGBMClassifier(**params_n)
                self.model_normal.fit(X, y_normal, sample_weight=sample_weights)
            else:
                self.model_normal.fit(X, y_normal, sample_weight=sample_weights, init_model=self.model_normal)
                
            if progress_callback:
                progress_callback(chunk_idx, total_chunks)
                
            chunk_idx += 1
            del df, X, y_normal, sample_weights
            gc.collect()
            
        self.save_models()
        return True

    def train_runner_mode(self, data_generator, total_chunks=1, progress_callback=None):
        import gc
        logging.info("Training LightGBM Runner Mode (Trend/H4) with RLHF & PnL Feedback (Optuna Auto-Tuning).")
        
        best_params_runner = None
        approved_ids, rejected_ids, hard_negative_ids, pnl_df = self._fetch_rlhf_pnl_data()

        chunk_idx = 1
        for df in data_generator:
            if df.empty:
                continue
                
            df = self.generate_targets(df)
            reentry_sell_mask = df['high'] >= df[['LWMA_5_High', 'LWMA_10_High']].min(axis=1)
            reentry_buy_mask = df['low'] <= df[['LWMA_5_Low', 'LWMA_10_Low']].max(axis=1)
            df = df[reentry_sell_mask | reentry_buy_mask].copy()

            if df.empty or len(df) < 50:
                continue
                
            forbidden_exact = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume']
            forbidden_cols = []
            # Runner mode memuat semua timeframe hingga H4
            for tf in ['', '_m5', '_m15', '_h1', '_h4']:
                for c in forbidden_exact:
                    forbidden_cols.append(f"{c}{tf}")
                for c in ['SMA_20', 'BB_Upper', 'BB_Lower', 'EMA_50', 'LWMA_5_High', 'LWMA_10_High', 'LWMA_5_Low', 'LWMA_10_Low']:
                    forbidden_cols.append(f"{c}{tf}")

            self.features = [col for col in df.columns if col not in forbidden_cols and 'Target' not in col]
            
            for col in self.features:
                if df[col].dtype == 'object':
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    
            X = df[self.features]
            y_runner = df['Target_Runner']
            
            sample_weights = np.ones(len(df), dtype=float)
            if approved_ids or rejected_ids or hard_negative_ids:
                for i in range(len(df)):
                    row_id_str = str(df.index[i])
                    row_time_str = df.index[i].strftime("%Y-%m-%d %H:%M:%S") if hasattr(df.index[i], "strftime") else row_id_str
                    if row_id_str in hard_negative_ids or row_time_str in hard_negative_ids:
                        sample_weights[i] = 3.0
                    elif row_id_str in approved_ids or row_time_str in approved_ids:
                        sample_weights[i] = 5.0
                    elif row_id_str in rejected_ids or row_time_str in rejected_ids:
                        sample_weights[i] = 0.1

            if not pnl_df.empty:
                if 'time' in df.columns:
                    df_time_floor = pd.to_datetime(df['time']).dt.floor('Min')
                else:
                    df_time_floor = pd.to_datetime(df.index).floor('Min')
                pnl_time_floor = pnl_df['time'].dt.floor('Min')
                for pnl_idx, pnl_row in pnl_df.iterrows():
                    match_idx = np.where(df_time_floor == pnl_time_floor[pnl_idx])[0]
                    if len(match_idx) > 0:
                        idx = match_idx[0]
                        if pnl_row['profit'] < 0:
                            sample_weights[idx] = 0.5
                        elif pnl_row['profit'] > 0:
                            sample_weights[idx] = 1.5

            if chunk_idx == 1 and len(X) > 100:
                best_params_runner = self.optimize_hyperparameters(X, y_runner, sample_weights, n_trials=30)
                
            params_r = best_params_runner if best_params_runner else {
                'n_estimators': 150, 'learning_rate': 0.03, 'max_depth': 5, 'num_leaves': 20,
                'min_child_samples': 40, 'subsample': 0.8, 'colsample_bytree': 0.8, 'random_state': 42
            }
            params_r['verbose'] = -1

            if self.model_runner is None:
                self.model_runner = lgb.LGBMClassifier(**params_r)
                self.model_runner.fit(X, y_runner, sample_weight=sample_weights)
            else:
                self.model_runner.fit(X, y_runner, sample_weight=sample_weights, init_model=self.model_runner)
                
            if progress_callback:
                progress_callback(chunk_idx, total_chunks)
                
            chunk_idx += 1
            del df, X, y_runner, sample_weights
            gc.collect()
            
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
        (Digunakan untuk pemicu Dynamic Exhaustion Exit & Entry Signal).
        """
        if self.model_normal is None or self.model_runner is None:
            return {"normal_buy": 0.0, "normal_sell": 0.0, "runner_buy": 0.0, "runner_sell": 0.0}

        # Filter kolom fitur yang valid
        if isinstance(X_live, pd.Series):
            X_live = pd.DataFrame([X_live])
            
        valid_cols = [c for c in self.features if c in X_live.columns]
        if not valid_cols:
            return {"normal_buy": 0.0, "normal_sell": 0.0, "runner_buy": 0.0, "runner_sell": 0.0}

        try:
            X_eval = X_live[valid_cols]
            probs_n = self.model_normal.predict_proba(X_eval)[0]
            probs_r = self.model_runner.predict_proba(X_eval)[0]
            
            # Support untuk Multiclass (3 kelas: 0=Fail, 1=Buy, 2=Sell)
            if len(probs_n) >= 3:
                pn_buy, pn_sell = float(probs_n[1]), float(probs_n[2])
            else:
                pn_buy = float(probs_n[1]) if len(probs_n) > 1 else 0.0
                pn_sell = 0.0
                
            if len(probs_r) >= 3:
                pr_buy, pr_sell = float(probs_r[1]), float(probs_r[2])
            else:
                pr_buy = float(probs_r[1]) if len(probs_r) > 1 else 0.0
                pr_sell = 0.0

            return {
                "normal_buy": pn_buy, 
                "normal_sell": pn_sell,
                "runner_buy": pr_buy, 
                "runner_sell": pr_sell
            }
        except Exception as e:
            logging.debug(f"Gagal kalkulasi live probabilities: {e}")
            return {"normal_buy": 0.0, "normal_sell": 0.0, "runner_buy": 0.0, "runner_sell": 0.0}
