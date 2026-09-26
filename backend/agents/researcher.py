import logging
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import numpy as np
import pandas as pd
import os
import joblib
import json

logging.basicConfig(level=logging.INFO)

class ResearcherAgent:
    """
    Agent 2: The Researcher (Dual-Target AI Brain)
    Melatih algoritma (LightGBM) menggunakan target dinamis.
    """
    
    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = str(symbol or "XAUUSD").upper()
        self.model_normal = None
        self.model_runner = None
        self.features = []
        self.is_training_normal = False
        self.is_training_runner = False
        self.last_accuracy_normal = 0.0
        self.last_accuracy_runner = 0.0
        self.last_trained_normal = None
        self.last_trained_runner = None
        self.max_runner_rr = 5.0 # Maximum RR dinamis yang didapat dari proses belajar Runner
        self._models_cache = {}

    def set_symbol(self, symbol: str):
        """Beralih ke model pair tertentu dengan in-memory caching instan tanpa reload disk berulang."""
        clean_sym = str(symbol or "XAUUSD").upper()
        if self.symbol == clean_sym and (self.model_normal is not None or self.model_runner is not None):
            return

        # Simpan model saat ini ke cache jika ada
        if self.symbol:
            self._models_cache[self.symbol] = {
                "normal": self.model_normal,
                "runner": self.model_runner,
                "features": self.features,
                "last_accuracy_normal": self.last_accuracy_normal,
                "last_accuracy_runner": self.last_accuracy_runner,
                "last_trained_normal": self.last_trained_normal,
                "last_trained_runner": self.last_trained_runner,
                "max_runner_rr": self.max_runner_rr
            }

        self.symbol = clean_sym

        # Pulihkan dari cache jika sudah pernah dimuat
        if clean_sym in self._models_cache:
            c = self._models_cache[clean_sym]
            self.model_normal = c["normal"]
            self.model_runner = c["runner"]
            self.features = c.get("features", [])
            self.last_accuracy_normal = c["last_accuracy_normal"]
            self.last_accuracy_runner = c["last_accuracy_runner"]
            self.last_trained_normal = c["last_trained_normal"]
            self.last_trained_runner = c["last_trained_runner"]
            self.max_runner_rr = c["max_runner_rr"]
        else:
            self.model_normal = None
            self.model_runner = None
            self.features = []
            self.last_accuracy_normal = 0.0
            self.last_accuracy_runner = 0.0
            self.last_trained_normal = None
            self.last_trained_runner = None
            self.load_models()

    def get_model_dir(self) -> str:
        """Direktori subfolder khusus untuk pair bersangkutan (contoh: models/XAUUSD)."""
        d = os.path.join("models", self.symbol)
        os.makedirs(d, exist_ok=True)
        return d

    def get_model_path(self, mode: str) -> str:
        return os.path.join(self.get_model_dir(), f"model_{mode}.pkl")

    def get_metadata_path(self) -> str:
        return os.path.join(self.get_model_dir(), "models_metadata.json")
        
    def save_metadata(self):
        """Menyimpan akurasi dan metadata pelatihan ke file JSON agar persisten melintasi restart."""
        try:
            meta_path = self.get_metadata_path()
            meta = {
                "symbol": self.symbol,
                "normal": {
                    "last_accuracy": float(self.last_accuracy_normal),
                    "last_trained_at": self.last_trained_normal,
                    "trained": self.model_normal is not None
                },
                "runner": {
                    "last_accuracy": float(self.last_accuracy_runner),
                    "last_trained_at": self.last_trained_runner,
                    "trained": self.model_runner is not None,
                    "max_runner_rr": float(self.max_runner_rr)
                }
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
            logging.info(f"[RESEARCHER-{self.symbol}] Metadata akurasi tersimpan ke {meta_path} (Normal: {self.last_accuracy_normal*100:.1f}%, Runner: {self.last_accuracy_runner*100:.1f}%, Max RR: {self.max_runner_rr:.1f}R)")
        except Exception as e:
            logging.error(f"Failed to save models metadata for {self.symbol}: {e}")

    def save_models(self):
        try:
            self.get_model_dir()
            path_normal = self.get_model_path("normal")
            path_runner = self.get_model_path("runner")
            if self.model_normal is not None:
                joblib.dump(self.model_normal, path_normal)
            if self.model_runner is not None:
                joblib.dump(self.model_runner, path_runner)
            self.save_metadata()
            logging.info(f"Model checkpoints and metadata saved to '{self.get_model_dir()}' directory.")
        except Exception as e:
            logging.error(f"Failed to save models for {self.symbol}: {e}")

    def load_models(self):
        try:
            loaded_any = False
            path_normal = self.get_model_path("normal")
            path_runner = self.get_model_path("runner")
            meta_path = self.get_metadata_path()

            # Cek subfolder pair, atau fallback ke root models/ jika belum dipindahkan
            target_normal = path_normal if os.path.exists(path_normal) else "models/model_normal.pkl"
            target_runner = path_runner if os.path.exists(path_runner) else "models/model_runner.pkl"

            if os.path.exists(target_normal) and os.path.getsize(target_normal) > 100:
                self.model_normal = joblib.load(target_normal)
                loaded_any = True
                logging.info(f"[RESEARCHER-{self.symbol}] Model Normal loaded from {target_normal}")

            if os.path.exists(target_runner) and os.path.getsize(target_runner) > 100:
                self.model_runner = joblib.load(target_runner)
                loaded_any = True
                logging.info(f"[RESEARCHER-{self.symbol}] Model Runner loaded from {target_runner}")

            if loaded_any:
                if self.model_normal is not None:
                    if hasattr(self.model_normal, 'feature_name_'):
                        self.features = list(self.model_normal.feature_name_)
                    elif hasattr(self.model_normal, 'booster_'):
                        self.features = self.model_normal.booster_.feature_name()
                elif self.model_runner is not None:
                    if hasattr(self.model_runner, 'feature_name_'):
                        self.features = list(self.model_runner.feature_name_)
                    elif hasattr(self.model_runner, 'booster_'):
                        self.features = self.model_runner.booster_.feature_name()

                # Baca metadata akurasi persisten jika tersedia
                target_meta = meta_path if os.path.exists(meta_path) else "models/models_metadata.json"
                if os.path.exists(target_meta):
                    try:
                        with open(target_meta, "r") as f:
                            meta = json.load(f)
                        self.last_accuracy_normal = float(meta.get("normal", {}).get("last_accuracy", 0.0))
                        self.last_trained_normal = meta.get("normal", {}).get("last_trained_at")
                        self.last_accuracy_runner = float(meta.get("runner", {}).get("last_accuracy", 0.0))
                        self.last_trained_runner = meta.get("runner", {}).get("last_trained_at")
                        self.max_runner_rr = float(meta.get("runner", {}).get("max_runner_rr", 5.0))
                        logging.info(f"[RESEARCHER-{self.symbol}] Metadata loaded: Normal Acc={self.last_accuracy_normal*100:.1f}%, Runner Acc={self.last_accuracy_runner*100:.1f}%, Max Runner RR={self.max_runner_rr:.1f}R")
                    except Exception as em:
                        logging.warning(f"Gagal membaca metadata {target_meta}: {em}")


                logging.info("Model checkpoints loaded successfully.")
                return True
        except Exception as e:
            logging.error(f"Failed to load models: {e}")
        return False
        
    def generate_targets(self, df):
        from .research.target_labeler import generate_targets
        return generate_targets(df, max_runner_rr=getattr(self, 'max_runner_rr', 5.0))


    def optimize_hyperparameters(self, X, y, sample_weights, mode="normal", n_trials=25):
        import optuna
        
        # Split subset of data for fast evaluation
        X_train, X_val, y_train, y_val, sw_train, sw_val = train_test_split(
            X, y, sample_weights, test_size=0.25, shuffle=False
        )

        from config import Config
        import os
        from dotenv import load_dotenv
        load_dotenv(override=True)
        if mode == "runner":
            entry_thresh = float(os.getenv("AI_RUNNER_ENTRY_THRESHOLD", getattr(Config, 'AI_RUNNER_ENTRY_THRESHOLD', 55.0))) / 100.0
        else:
            entry_thresh = float(os.getenv("AI_NORMAL_ENTRY_THRESHOLD", getattr(Config, 'AI_NORMAL_ENTRY_THRESHOLD', 60.0))) / 100.0

        def objective(trial):
            params = {
                'n_estimators': trial.suggest_int('n_estimators', 80, 200),
                'learning_rate': trial.suggest_float('learning_rate', 0.02, 0.08, log=True),
                'max_depth': trial.suggest_int('max_depth', 4, 7),
                'num_leaves': trial.suggest_int('num_leaves', 15, 45),
                'min_child_samples': trial.suggest_int('min_child_samples', 30, 100),
                'subsample': trial.suggest_float('subsample', 0.65, 0.95),
                'colsample_bytree': trial.suggest_float('colsample_bytree', 0.65, 0.95),
                'reg_alpha': trial.suggest_float('reg_alpha', 1e-3, 5.0, log=True),
                'reg_lambda': trial.suggest_float('reg_lambda', 1e-3, 5.0, log=True),
                'min_split_gain': trial.suggest_float('min_split_gain', 0.0, 0.5),
                'class_weight': 'balanced',
                'random_state': 42,
                'verbose': -1
            }
            
            model = lgb.LGBMClassifier(**params)
            model.fit(X_train, y_train, sample_weight=sw_train)
            
            if hasattr(model, 'predict_proba'):
                probs = model.predict_proba(X_val)
                classes = list(getattr(model, 'classes_', [0, 1, 2]))
                idx_buy = classes.index(1) if 1 in classes else -1
                idx_sell = classes.index(2) if 2 in classes else -1
                
                preds = np.zeros(len(X_val), dtype=int)
                for i in range(len(X_val)):
                    pb = probs[i][idx_buy] if idx_buy != -1 and idx_buy < len(probs[i]) else 0.0
                    ps = probs[i][idx_sell] if idx_sell != -1 and idx_sell < len(probs[i]) else 0.0
                    if pb >= entry_thresh and pb > ps:
                        preds[i] = 1
                    elif ps >= entry_thresh and ps > pb:
                        preds[i] = 2
            else:
                preds = model.predict(X_val)

            trade_mask = (preds == 1) | (preds == 2)
            n_trades = int(trade_mask.sum())
            if n_trades >= 30:
                y_val_arr = y_val.values if hasattr(y_val, 'values') else np.array(y_val)
                trade_wr = float((preds[trade_mask] == y_val_arr[trade_mask]).mean())
                return trade_wr
            else:
                # Penalti keras jika model takut masuk posisi atau sinyal terlalu sedikit
                return 0.0
            
        study = optuna.create_study(direction='maximize')
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        study.optimize(objective, n_trials=n_trials)
        
        logging.info(f"[{mode.upper()} OPTUNA] Best Trial Win Rate: {study.best_value * 100:.2f}% | Best Params: {study.best_params}")
        return study.best_params

    def _fetch_rlhf_pnl_data(self, mode="normal"):
        try:
            from database import get_approved_setup_ids, get_rejected_setup_ids, get_historical_pnl_feedback, get_hard_negative_ids
            mode_str = mode.lower() if mode else "normal"
            approved_ids = set(get_approved_setup_ids(mode=mode_str))
            rejected_ids = set(get_rejected_setup_ids(mode=mode_str))
            hard_negative_ids = set(get_hard_negative_ids(mode=mode_str))
            pnl_df = get_historical_pnl_feedback(mode=mode_str)
            logging.info(f"[{mode_str.upper()}] Loaded RLHF: {len(approved_ids)} approved, {len(rejected_ids)} rejected, {len(hard_negative_ids)} hard negatives, {len(pnl_df)} trade logs")
        except Exception as e:
            logging.error(f"Failed to fetch RLHF/PnL data ({mode}): {e}")
            approved_ids, rejected_ids, hard_negative_ids = set(), set(), set()
            pnl_df = pd.DataFrame()
        return approved_ids, rejected_ids, hard_negative_ids, pnl_df

    def train_normal_mode(self, data_generator, total_chunks=1, progress_callback=None):
        import gc
        self.is_training_normal = True
        logging.info("Training LightGBM Normal Mode (Scalping) with RLHF & PnL Feedback (Optuna Auto-Tuning).")
        
        best_params_normal = None
        approved_ids, rejected_ids, hard_negative_ids, pnl_df = self._fetch_rlhf_pnl_data(mode="normal")
        chunk_idx = 1
        for df in data_generator:
            if df.empty:
                continue
                
            logging.info(f"[Normal Mode] Memproses Chunk {chunk_idx}/{total_chunks}...")
                
            is_live_feedback = '_sample_weight' in df.columns
            if is_live_feedback:
                logging.info(f"[Normal Mode] Menginjeksi Real-Trade Live Feedback ({len(df)} sampel tertutup)...")
                sample_weights = df['_sample_weight'].to_numpy(dtype=float)
                y_normal = df['Target_Normal']
            else:
                df = self.generate_targets(df)
                lwma_low_zone = np.maximum(df['LWMA_5_Low'].values, df['LWMA_10_Low'].values)
                lwma_high_zone = np.minimum(df['LWMA_5_High'].values, df['LWMA_10_High'].values)
                sma_20_vals = df['SMA_20'].values if 'SMA_20' in df.columns else df['close'].values
                ema_50_vals = df['EMA_50'].values if 'EMA_50' in df.columns else df['close'].values
                bb_upper_vals = df['BB_Upper'].values if 'BB_Upper' in df.columns else df['close'].values
                bb_lower_vals = df['BB_Lower'].values if 'BB_Lower' in df.columns else df['close'].values

                open_vals = df['open'].values if 'open' in df.columns else df['close'].values
                reentry_buy_mask = (df['low'].values <= lwma_low_zone) & (df['close'].values >= sma_20_vals) & (df['close'].values <= bb_upper_vals) & (sma_20_vals >= ema_50_vals) & (df['close'].values >= ema_50_vals) & (df['close'].values >= open_vals)
                reentry_sell_mask = (df['high'].values >= lwma_high_zone) & (df['close'].values <= sma_20_vals) & (df['close'].values >= bb_lower_vals) & (sma_20_vals <= ema_50_vals) & (df['close'].values <= ema_50_vals) & (df['close'].values <= open_vals)
                df = df[reentry_buy_mask | reentry_sell_mask].copy()

                if df.empty or len(df) < 50:
                    continue
                y_normal = df['Target_Normal']

            forbidden_exact = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume', 'symbol', 'time', 'timestamp', 'datetime', 'date', 'id']
            forbidden_cols = set()
            # Isolasi Dataset: Normal Mode tidak memuat fitur kompleks H4 untuk menghemat memori drastis
            for tf in ['', '_m5', '_m15']:
                for c in forbidden_exact:
                    forbidden_cols.add(f"{c}{tf}")
                for c in ['SMA_20', 'BB_Upper', 'BB_Lower', 'EMA_50', 'LWMA_5_High', 'LWMA_10_High', 'LWMA_5_Low', 'LWMA_10_Low']:
                    forbidden_cols.add(f"{c}{tf}")

            if not getattr(self, 'features', None) or (chunk_idx == 1 and not is_live_feedback):
                candidate_features = []
                for col in df.columns:
                    if col in forbidden_cols or 'Target' in col or col.startswith('_'):
                        continue
                    if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
                        candidate_features.append(col)
                    else:
                        coerced = pd.to_numeric(df[col], errors='coerce')
                        if not coerced.isna().all():
                            candidate_features.append(col)
                self.features = candidate_features
            
            # Lock fitur agar seragam dengan chunk pertama (mencegah crash LightGBM "features in data is not the same")
            for col in self.features:
                if col not in df.columns:
                    df[col] = 0.0
                elif not (pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col])):
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                    
            X = df[self.features]
            
            if not is_live_feedback:
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
                    df_times = pd.to_datetime(df['time'] if 'time' in df.columns else df.index)
                    if hasattr(df_times, 'dt') and hasattr(df_times.dt, 'tz') and df_times.dt.tz is not None:
                        df_times = df_times.dt.tz_localize(None)
                    df_time_floor = df_times.dt.floor('min') if hasattr(df_times, 'dt') else df_times.floor('min')
                    
                    for _, pnl_row in pnl_df.iterrows():
                        p_time = pd.to_datetime(pnl_row['time'])
                        if hasattr(p_time, 'tzinfo') and p_time.tzinfo is not None:
                            p_time = p_time.tz_localize(None)
                        p_time_floor = p_time.floor('min')
                        match_idx = np.where(df_time_floor == p_time_floor)[0]
                        if len(match_idx) > 0:
                            idx = match_idx[0]
                            if pnl_row['profit'] < 0:
                                sample_weights[idx] = 0.5
                            elif pnl_row['profit'] > 0:
                                sample_weights[idx] = 1.5

                # Regime-Aware Sample Weighting: Normal Mode (Scalping 1:2 RR) diutamakan pada kondisi Non-Trending / Ranging
                if 'adx' in df.columns:
                    regime_weights = np.where(df['adx'] < 25.0, 1.25, 0.85)
                    sample_weights *= regime_weights

            if chunk_idx == 1 and len(X) > 100:
                best_params_normal = self.optimize_hyperparameters(X, y_normal, sample_weights, mode="normal", n_trials=25)
                
            params_n = best_params_normal.copy() if best_params_normal else {
                'n_estimators': 150, 'learning_rate': 0.03, 'max_depth': 5, 'num_leaves': 31,
                'min_child_samples': 30, 'subsample': 0.8, 'colsample_bytree': 0.8, 'random_state': 42
            }
            params_n['class_weight'] = 'balanced'
            params_n['verbose'] = -1
            params_n['random_state'] = 42

            if self.model_normal is None:
                base_est = params_n.get('n_estimators', 80)
                params_n['n_estimators'] = min(base_est, 100)
                self.model_normal = lgb.LGBMClassifier(**params_n)
                self.model_normal.fit(X, y_normal, sample_weight=sample_weights)
            else:
                base_est = getattr(self.model_normal, 'n_estimators', 80) or 80
                max_trees_cap = max(350, min(800, base_est + total_chunks * 5))
                tree_step = max(2, min(8, (max_trees_cap - 80) // max(total_chunks, 1)))
                curr_trees = getattr(self.model_normal, 'n_estimators', 80) or 80
                new_trees = min(curr_trees + tree_step, max_trees_cap)
                if new_trees > curr_trees:
                    self.model_normal.set_params(n_estimators=new_trees, verbose=-1)
                    booster = getattr(self.model_normal, 'booster_', None)
                    self.model_normal.fit(X, y_normal, sample_weight=sample_weights, init_model=booster)
                else:
                    self.model_normal.set_params(n_estimators=curr_trees + 1, verbose=-1)
                    booster = getattr(self.model_normal, 'booster_', None)
                    self.model_normal.fit(X, y_normal, sample_weight=sample_weights, init_model=booster)
                
            if progress_callback:
                progress_callback(chunk_idx, total_chunks)
                
            chunk_idx += 1
            del df, X, y_normal, sample_weights
            gc.collect()
            
        if chunk_idx == 1:
            logging.warning("⚠️ Batal Training (Normal Mode): Database market_data KOSONG. Silakan tekan tombol 'Force Backfill MT5' terlebih dahulu!")
            self.is_training_normal = False
            return False

        self.save_models()
        self.is_training_normal = False
        return True

    def train_runner_mode(self, data_generator, total_chunks=1, progress_callback=None):
        import gc
        self.is_training_runner = True
        logging.info("Training LightGBM Runner Mode (Trend/H4) with RLHF & PnL Feedback (Optuna Auto-Tuning).")
        
        best_params_runner = None
        approved_ids, rejected_ids, hard_negative_ids, pnl_df = self._fetch_rlhf_pnl_data(mode="runner")
        chunk_idx = 1
        for df in data_generator:
            if df.empty:
                continue
                
            logging.info(f"[Runner Mode] Memproses Chunk {chunk_idx}/{total_chunks}...")
                
            is_live_feedback = '_sample_weight' in df.columns
            if is_live_feedback:
                logging.info(f"[Runner Mode] Menginjeksi Real-Trade Live Feedback ({len(df)} sampel tertutup)...")
                sample_weights = df['_sample_weight'].to_numpy(dtype=float)
                y_runner = df['Target_Runner']
            else:
                df = self.generate_targets(df)
                lwma_low_zone = np.maximum(df['LWMA_5_Low'].values, df['LWMA_10_Low'].values)
                lwma_high_zone = np.minimum(df['LWMA_5_High'].values, df['LWMA_10_High'].values)
                sma_20_vals = df['SMA_20'].values if 'SMA_20' in df.columns else df['close'].values
                ema_50_vals = df['EMA_50'].values if 'EMA_50' in df.columns else df['close'].values
                bb_upper_vals = df['BB_Upper'].values if 'BB_Upper' in df.columns else df['close'].values
                bb_lower_vals = df['BB_Lower'].values if 'BB_Lower' in df.columns else df['close'].values

                open_vals = df['open'].values if 'open' in df.columns else df['close'].values
                reentry_buy_mask = (df['low'].values <= lwma_low_zone) & (df['close'].values >= sma_20_vals) & (df['close'].values <= bb_upper_vals) & (sma_20_vals >= ema_50_vals) & (df['close'].values >= ema_50_vals) & (df['close'].values >= open_vals)
                reentry_sell_mask = (df['high'].values >= lwma_high_zone) & (df['close'].values <= sma_20_vals) & (df['close'].values >= bb_lower_vals) & (sma_20_vals <= ema_50_vals) & (df['close'].values <= ema_50_vals) & (df['close'].values <= open_vals)
                df = df[reentry_buy_mask | reentry_sell_mask].copy()

                if df.empty or len(df) < 50:
                    continue
                y_runner = df['Target_Runner']

            forbidden_exact = ['open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume', 'symbol', 'time', 'timestamp', 'datetime', 'date', 'id']
            forbidden_cols = set()
            # Runner mode memuat semua timeframe hingga H4
            for tf in ['', '_m5', '_m15']:
                for c in forbidden_exact:
                    forbidden_cols.add(f"{c}{tf}")
                for c in ['SMA_20', 'BB_Upper', 'BB_Lower', 'EMA_50', 'LWMA_5_High', 'LWMA_10_High', 'LWMA_5_Low', 'LWMA_10_Low']:
                    forbidden_cols.add(f"{c}{tf}")

            if not getattr(self, 'features', None) or (chunk_idx == 1 and not is_live_feedback):
                candidate_features = []
                for col in df.columns:
                    if col in forbidden_cols or 'Target' in col or col.startswith('_'):
                        continue
                    if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
                        candidate_features.append(col)
                    else:
                        coerced = pd.to_numeric(df[col], errors='coerce')
                        if not coerced.isna().all():
                            candidate_features.append(col)
                self.features = candidate_features
            
            for col in self.features:
                if col not in df.columns:
                    df[col] = 0.0
                elif not (pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col])):
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
                    
            X = df[self.features]
            
            if not is_live_feedback:
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
                    df_times = pd.to_datetime(df['time'] if 'time' in df.columns else df.index)
                    if hasattr(df_times, 'dt') and hasattr(df_times.dt, 'tz') and df_times.dt.tz is not None:
                        df_times = df_times.dt.tz_localize(None)
                    df_time_floor = df_times.dt.floor('min') if hasattr(df_times, 'dt') else df_times.floor('min')
                    
                    for _, pnl_row in pnl_df.iterrows():
                        p_time = pd.to_datetime(pnl_row['time'])
                        if hasattr(p_time, 'tzinfo') and p_time.tzinfo is not None:
                            p_time = p_time.tz_localize(None)
                        p_time_floor = p_time.floor('min')
                        match_idx = np.where(df_time_floor == p_time_floor)[0]
                        if len(match_idx) > 0:
                            idx = match_idx[0]
                            if pnl_row['profit'] < 0:
                                sample_weights[idx] = 0.5
                            elif pnl_row['profit'] > 0:
                                sample_weights[idx] = 1.5

                # Regime-Aware Sample Weighting: Runner Mode (Trend 1:5 RR) diutamakan pada kondisi Trending Kuat (ADX >= 25)
                if 'adx' in df.columns:
                    regime_weights = np.where(df['adx'] >= 25.0, 1.35, 0.75)
                    sample_weights *= regime_weights

            if chunk_idx == 1 and len(X) > 100:
                best_params_runner = self.optimize_hyperparameters(X, y_runner, sample_weights, mode="runner", n_trials=25)
                
            params_r = best_params_runner.copy() if best_params_runner else {
                'n_estimators': 150, 'learning_rate': 0.03, 'max_depth': 5, 'num_leaves': 31,
                'min_child_samples': 30, 'subsample': 0.8, 'colsample_bytree': 0.8, 'random_state': 42
            }
            params_r['class_weight'] = 'balanced'
            params_r['verbose'] = -1
            params_r['random_state'] = 42

            if self.model_runner is None:
                base_est = params_r.get('n_estimators', 100)
                params_r['n_estimators'] = min(base_est, 120)
                self.model_runner = lgb.LGBMClassifier(**params_r)
                self.model_runner.fit(X, y_runner, sample_weight=sample_weights)
            else:
                base_est = getattr(self.model_runner, 'n_estimators', 100) or 100
                max_trees_cap = max(400, min(800, base_est + total_chunks * 5))
                tree_step = max(2, min(8, (max_trees_cap - 100) // max(total_chunks, 1)))
                curr_trees = getattr(self.model_runner, 'n_estimators', 100) or 100
                new_trees = min(curr_trees + tree_step, max_trees_cap)
                if new_trees > curr_trees:
                    self.model_runner.set_params(n_estimators=new_trees, verbose=-1)
                    booster = getattr(self.model_runner, 'booster_', None)
                    self.model_runner.fit(X, y_runner, sample_weight=sample_weights, init_model=booster)
                else:
                    self.model_runner.set_params(n_estimators=curr_trees + 1, verbose=-1)
                    booster = getattr(self.model_runner, 'booster_', None)
                    self.model_runner.fit(X, y_runner, sample_weight=sample_weights, init_model=booster)
                
            if progress_callback:
                progress_callback(chunk_idx, total_chunks)
                
            chunk_idx += 1
            del df, X, y_runner, sample_weights
            gc.collect()
            
        if chunk_idx == 1:
            logging.warning("⚠️ Batal Training (Runner Mode): Database market_data KOSONG. Silakan tekan tombol 'Force Backfill MT5' terlebih dahulu!")
            self.is_training_runner = False
            return False

        self.save_models()
        self.is_training_runner = False
        return True

    def micro_retrain(self, mode: str, df_recent: pd.DataFrame, live_feedback_df: pd.DataFrame = None):
        """
        Online Learning (Micro-Retrain):
        Melatih incremental model secara cepat (warm-start init_model) dengan data candle terbaru
        dan live decision feedback tanpa memakan waktu Optuna.
        """
        import gc
        mode_str = mode.lower()
        if mode_str == "normal":
            self.is_training_normal = True
        else:
            self.is_training_runner = True

        try:
            current_model = self.model_normal if mode_str == "normal" else self.model_runner
            if current_model is None:
                logging.warning(f"[MICRO-RETRAIN] Model {mode_str.upper()} belum pernah dilatih (None). Lakukan Full/Initial Train terlebih dahulu.")
                return False

            if df_recent is None or df_recent.empty:
                logging.warning(f"[MICRO-RETRAIN] Data candle recent kosong untuk {mode_str.upper()}.")
                return False

            # 1. Target generation & filter BBMA Re-entry (Slide 20, 21, 33, 51-56)
            df = self.generate_targets(df_recent.copy())
            lwma_low_zone = np.maximum(df['LWMA_5_Low'].values, df['LWMA_10_Low'].values) if 'LWMA_5_Low' in df.columns else df['low'].values
            lwma_high_zone = np.minimum(df['LWMA_5_High'].values, df['LWMA_10_High'].values) if 'LWMA_5_High' in df.columns else df['high'].values
            sma_20_vals = df['SMA_20'].values if 'SMA_20' in df.columns else df['close'].values
            ema_50_vals = df['EMA_50'].values if 'EMA_50' in df.columns else df['close'].values
            bb_upper_vals = df['BB_Upper'].values if 'BB_Upper' in df.columns else df['close'].values
            bb_lower_vals = df['BB_Lower'].values if 'BB_Lower' in df.columns else df['close'].values

            open_vals = df['open'].values if 'open' in df.columns else df['close'].values
            reentry_buy_mask = (df['low'].values <= lwma_low_zone) & (df['close'].values >= sma_20_vals) & (df['close'].values <= bb_upper_vals) & (sma_20_vals >= ema_50_vals) & (df['close'].values >= ema_50_vals) & (df['close'].values >= open_vals)
            reentry_sell_mask = (df['high'].values >= lwma_high_zone) & (df['close'].values <= sma_20_vals) & (df['close'].values >= bb_lower_vals) & (sma_20_vals <= ema_50_vals) & (df['close'].values <= ema_50_vals) & (df['close'].values <= open_vals)
            df = df[reentry_buy_mask | reentry_sell_mask].copy()

            if df.empty or len(df) < 20:
                logging.info(f"[MICRO-RETRAIN] Terlalu sedikit sampel re-entry ({len(df)}) untuk {mode_str.upper()}. Lewati.")
                return False

            target_col = 'Target_Normal' if mode_str == 'normal' else 'Target_Runner'
            y = df[target_col]

            # 2. Fitur locking sesuai model yang sedang aktif
            if not getattr(self, 'features', None):
                if hasattr(current_model, 'feature_name_'):
                    self.features = list(current_model.feature_name_)
                elif hasattr(current_model, 'booster_'):
                    self.features = current_model.booster_.feature_name()

            for col in self.features:
                if col not in df.columns:
                    df[col] = 0.0
                elif not (pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col])):
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

            X = df[self.features].copy()
            sample_weights = np.ones(len(df), dtype=float)

            # Regime weighting
            if 'adx' in df.columns:
                if mode_str == 'normal':
                    sample_weights *= np.where(df['adx'] < 25.0, 1.25, 0.85)
                else:
                    sample_weights *= np.where(df['adx'] >= 25.0, 1.35, 0.75)

            # Injeksi live trade feedback bila ada
            if live_feedback_df is not None and not live_feedback_df.empty:
                fb_df = live_feedback_df.copy()
                for col in self.features:
                    if col not in fb_df.columns:
                        fb_df[col] = 0.0
                    elif not (pd.api.types.is_numeric_dtype(fb_df[col]) or pd.api.types.is_bool_dtype(fb_df[col])):
                        fb_df[col] = pd.to_numeric(fb_df[col], errors='coerce').fillna(0.0)
                
                if target_col in fb_df.columns:
                    X_fb = fb_df[self.features]
                    y_fb = fb_df[target_col]
                    sw_fb = fb_df['_sample_weight'].to_numpy(dtype=float) if '_sample_weight' in fb_df.columns else np.ones(len(fb_df)) * 2.0
                    
                    X = pd.concat([X, X_fb], ignore_index=True)
                    y = pd.concat([y, y_fb], ignore_index=True)
                    sample_weights = np.concatenate([sample_weights, sw_fb])

            # 3. Incremental Warm-Start Fit (Ringan: n_estimators bertambah 15 pohon)
            current_n_est = getattr(current_model, 'n_estimators', 100) or 100
            new_n_est = current_n_est + 15
            current_model.set_params(n_estimators=new_n_est, verbose=-1)
            current_model.fit(X, y, sample_weight=sample_weights, init_model=current_model)

            logging.info(f"[MICRO-RETRAIN] ✅ Berhasil update model {mode_str.upper()} secara inkremental ({len(X)} sampel, total pohon: {new_n_est}).")

            # 4. Simpan model checkpoint
            self.save_models()
            return True
        except Exception as e:
            logging.error(f"[MICRO-RETRAIN] Gagal micro retrain {mode_str}: {e}")
            return False
        finally:
            if mode_str == "normal":
                self.is_training_normal = False
            else:
                self.is_training_runner = False
            gc.collect()


    def get_top_feature_contributions(self, X_row, top_n=3):
        """
        XAI (Explainable AI):
        Mengekstrak Top 3 Feature Contributions dari model LightGBM untuk keputusan eksekusi.
        """
        from .research.explainer import get_top_feature_contributions
        return get_top_feature_contributions(self.model_normal, self.features, X_row, top_n=top_n)


    def get_live_probabilities(self, X_live):
        """
        Membaca skor probabilitas seketika (live) dari model yang telah dilatih
        (Digunakan untuk pemicu Dynamic Exhaustion Exit & Entry Signal).
        Mendukung evaluasi mandiri (Normal tetap aktif meski Runner belum dilatih, dan sebaliknya).
        """
        if self.model_normal is None and self.model_runner is None:
            return {"normal_buy": 0.0, "normal_sell": 0.0, "runner_buy": 0.0, "runner_sell": 0.0, "normal": 0.0, "runner": 0.0}

        # Filter kolom fitur yang valid
        if isinstance(X_live, pd.Series):
            X_live = pd.DataFrame([X_live])
            
        valid_cols = [c for c in self.features if c in X_live.columns]
        if not valid_cols:
            return {"normal_buy": 0.0, "normal_sell": 0.0, "runner_buy": 0.0, "runner_sell": 0.0, "normal": 0.0, "runner": 0.0}

        try:
            X_eval = X_live[valid_cols].copy()
            for c in valid_cols:
                if not (pd.api.types.is_numeric_dtype(X_eval[c]) or pd.api.types.is_bool_dtype(X_eval[c])):
                    X_eval[c] = pd.to_numeric(X_eval[c], errors='coerce').fillna(0.0)
            pn_buy, pn_sell = 0.0, 0.0
            pr_buy, pr_sell = 0.0, 0.0

            if self.model_normal is not None:
                probs_n = self.model_normal.predict_proba(X_eval)[0]
                classes_n = list(getattr(self.model_normal, 'classes_', [0, 1, 2]))
                idx_n_b = classes_n.index(1) if 1 in classes_n else -1
                idx_n_s = classes_n.index(2) if 2 in classes_n else -1
                pn_buy = float(probs_n[idx_n_b]) if idx_n_b != -1 and idx_n_b < len(probs_n) else 0.0
                pn_sell = float(probs_n[idx_n_s]) if idx_n_s != -1 and idx_n_s < len(probs_n) else 0.0

            if self.model_runner is not None:
                probs_r = self.model_runner.predict_proba(X_eval)[0]
                classes_r = list(getattr(self.model_runner, 'classes_', [0, 1, 2]))
                idx_r_b = classes_r.index(1) if 1 in classes_r else -1
                idx_r_s = classes_r.index(2) if 2 in classes_r else -1
                pr_buy = float(probs_r[idx_r_b]) if idx_r_b != -1 and idx_r_b < len(probs_r) else 0.0
                pr_sell = float(probs_r[idx_r_s]) if idx_r_s != -1 and idx_r_s < len(probs_r) else 0.0

            return {
                "normal_buy": pn_buy, 
                "normal_sell": pn_sell,
                "runner_buy": pr_buy, 
                "runner_sell": pr_sell,
                "normal": max(pn_buy, pn_sell),
                "runner": max(pr_buy, pr_sell)
            }
        except Exception as e:
            logging.debug(f"Gagal kalkulasi live probabilities: {e}")
            return {"normal_buy": 0.0, "normal_sell": 0.0, "runner_buy": 0.0, "runner_sell": 0.0, "normal": 0.0, "runner": 0.0}
