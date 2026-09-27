import os
import gc
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
import lightgbm as lgb

from .research import (
    generate_targets,
    get_top_feature_contributions,
    add_normalized_features,
    extract_and_lock_features,
    optimize_hyperparameters,
    calibrate_optimal_threshold,
    ModelManager,
)

logger = logging.getLogger(__name__)


class ResearcherAgent:
    """
    Agent 2: The Researcher (Dual-Target AI Brain)
    Orkestrator pelatihan LightGBM (Normal Scalping & Dynamic Runner)
    menggunakan arsitektur modular di backend/agents/research/.
    """

    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = str(symbol or "XAUUSD").upper()
        self.model_normal = None
        self.model_runner = None
        self.features: List[str] = []
        self.is_training_normal = False
        self.is_training_runner = False
        self.last_accuracy_normal = 0.0
        self.last_accuracy_runner = 0.0
        self.last_trained_normal = None
        self.last_trained_runner = None
        self.optimal_threshold_normal = 0.54
        self.optimal_threshold_runner = 0.54
        self.max_runner_rr = 5.0
        self._models_cache: Dict[str, Dict[str, Any]] = {}

    # ---------------------------------------------------------------------------------
    # MODEL PERSISTENCE & CACHING (Delegates to ModelManager)
    # ---------------------------------------------------------------------------------
    def set_symbol(self, symbol: str):
        """Beralih ke model pair tertentu dengan in-memory caching instan tanpa reload disk berulang."""
        clean_sym = str(symbol or "XAUUSD").upper()
        if self.symbol == clean_sym and (self.model_normal is not None or self.model_runner is not None):
            return

        if self.symbol:
            self._models_cache[self.symbol] = {
                "normal": self.model_normal,
                "runner": self.model_runner,
                "features": self.features,
                "last_accuracy_normal": self.last_accuracy_normal,
                "last_accuracy_runner": self.last_accuracy_runner,
                "last_trained_normal": self.last_trained_normal,
                "last_trained_runner": self.last_trained_runner,
                "optimal_threshold_normal": self.optimal_threshold_normal,
                "optimal_threshold_runner": self.optimal_threshold_runner,
                "max_runner_rr": self.max_runner_rr
            }

        self.symbol = clean_sym

        if clean_sym in self._models_cache:
            c = self._models_cache[clean_sym]
            self.model_normal = c["normal"]
            self.model_runner = c["runner"]
            self.features = c.get("features", [])
            self.last_accuracy_normal = c["last_accuracy_normal"]
            self.last_accuracy_runner = c["last_accuracy_runner"]
            self.last_trained_normal = c["last_trained_normal"]
            self.last_trained_runner = c["last_trained_runner"]
            self.optimal_threshold_normal = c.get("optimal_threshold_normal", 0.54)
            self.optimal_threshold_runner = c.get("optimal_threshold_runner", 0.54)
            self.max_runner_rr = c["max_runner_rr"]
        else:
            self.model_normal = None
            self.model_runner = None
            self.features = []
            self.last_accuracy_normal = 0.0
            self.last_accuracy_runner = 0.0
            self.last_trained_normal = None
            self.last_trained_runner = None
            self.optimal_threshold_normal = 0.54
            self.optimal_threshold_runner = 0.54
            self.load_models()

    def get_model_dir(self) -> str:
        return ModelManager.get_model_dir(self.symbol)

    def get_model_path(self, mode: str) -> str:
        return ModelManager.get_model_path(self.symbol, mode)

    def get_metadata_path(self) -> str:
        return ModelManager.get_metadata_path(self.symbol)

    def save_metadata(self):
        return ModelManager.save_metadata(
            symbol=self.symbol,
            normal_acc=self.last_accuracy_normal,
            normal_trained_at=self.last_trained_normal,
            normal_th=self.optimal_threshold_normal,
            normal_trained=self.model_normal is not None,
            runner_acc=self.last_accuracy_runner,
            runner_trained_at=self.last_trained_runner,
            runner_th=self.optimal_threshold_runner,
            runner_trained=self.model_runner is not None,
            max_runner_rr=self.max_runner_rr
        )

    def save_models(self):
        return ModelManager.save_models(
            symbol=self.symbol,
            model_normal=self.model_normal,
            model_runner=self.model_runner,
            normal_acc=self.last_accuracy_normal,
            normal_trained_at=self.last_trained_normal,
            normal_th=self.optimal_threshold_normal,
            runner_acc=self.last_accuracy_runner,
            runner_trained_at=self.last_trained_runner,
            runner_th=self.optimal_threshold_runner,
            max_runner_rr=self.max_runner_rr
        )

    def load_models(self) -> bool:
        loaded = ModelManager.load_models(self.symbol)
        if loaded.get("loaded", False):
            self.model_normal = loaded["model_normal"]
            self.model_runner = loaded["model_runner"]
            self.features = loaded.get("features", [])
            self.last_accuracy_normal = loaded["last_accuracy_normal"]
            self.last_trained_normal = loaded["last_trained_normal"]
            self.optimal_threshold_normal = loaded["optimal_threshold_normal"]
            self.last_accuracy_runner = loaded["last_accuracy_runner"]
            self.last_trained_runner = loaded["last_trained_runner"]
            self.optimal_threshold_runner = loaded["optimal_threshold_runner"]
            self.max_runner_rr = loaded["max_runner_rr"]
            return True
        return False

    # ---------------------------------------------------------------------------------
    # RESEARCH HELPERS (Delegates to Submodules)
    # ---------------------------------------------------------------------------------
    def generate_targets(self, df: pd.DataFrame) -> pd.DataFrame:
        return generate_targets(df, max_runner_rr=getattr(self, 'max_runner_rr', 5.0))

    def add_normalized_features(self, df: pd.DataFrame) -> pd.DataFrame:
        return add_normalized_features(df)

    def _extract_and_lock_features(self, df: pd.DataFrame, mode: str = "normal") -> List[str]:
        self.features = extract_and_lock_features(df, mode=mode)
        return self.features

    def optimize_hyperparameters(
        self,
        X: pd.DataFrame,
        y: Any,
        sample_weights: Any,
        mode: str = "normal",
        n_trials: int = 40,
        setup_directions: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        params = optimize_hyperparameters(
            X, y, sample_weights,
            mode=mode,
            n_trials=n_trials,
            setup_directions=setup_directions,
            symbol=self.symbol,
            max_runner_rr=getattr(self, 'max_runner_rr', 5.0)
        )
        if 'optimal_threshold' in params:
            if mode == 'normal':
                self.optimal_threshold_normal = float(params['optimal_threshold'])
            else:
                self.optimal_threshold_runner = float(params['optimal_threshold'])
        return params

    def calibrate_optimal_threshold(
        self,
        model: Any,
        X: pd.DataFrame,
        y: Any,
        mode: str = "normal",
        setup_directions: Optional[np.ndarray] = None,
        min_signals: int = 25
    ) -> float:
        th = calibrate_optimal_threshold(
            model, X, y,
            mode=mode,
            setup_directions=setup_directions,
            min_signals=min_signals,
            max_runner_rr=getattr(self, 'max_runner_rr', 5.0)
        )
        if mode == 'normal':
            self.optimal_threshold_normal = float(th)
        else:
            self.optimal_threshold_runner = float(th)
        return th

    def _fetch_rlhf_pnl_data(self, mode: str = "normal") -> Tuple[set, set, set, pd.DataFrame]:
        try:
            from database import get_approved_setup_ids, get_rejected_setup_ids, get_historical_pnl_feedback, get_hard_negative_ids
            mode_str = mode.lower() if mode else "normal"
            target_sym = (getattr(self, "symbol", "XAUUSD") or "XAUUSD").upper()
            approved_ids = set(get_approved_setup_ids(mode=mode_str, symbol=target_sym))
            rejected_ids = set(get_rejected_setup_ids(mode=mode_str, symbol=target_sym))
            hard_negative_ids = set(get_hard_negative_ids(mode=mode_str, symbol=target_sym))
            pnl_df = get_historical_pnl_feedback(mode=mode_str, symbol=target_sym)
            logger.info(f"[{mode_str.upper()} - {target_sym}] Loaded RLHF: {len(approved_ids)} approved, {len(rejected_ids)} rejected, {len(hard_negative_ids)} hard negatives, {len(pnl_df)} trade logs")
        except Exception as e:
            logger.error(f"Failed to fetch RLHF/PnL data ({mode} - {getattr(self, 'symbol', 'XAUUSD')}): {e}")
            approved_ids, rejected_ids, hard_negative_ids = set(), set(), set()
            pnl_df = pd.DataFrame()
        return approved_ids, rejected_ids, hard_negative_ids, pnl_df

    # ---------------------------------------------------------------------------------
    # CORE UNIFIED TRAINING PIPELINE (Normal & Runner)
    # ---------------------------------------------------------------------------------
    def _execute_training_pipeline(
        self,
        mode: str,
        data_generator,
        total_chunks: int = 1,
        progress_callback=None,
        data_miner=None
    ) -> bool:
        mode_str = mode.lower()
        is_normal = (mode_str == "normal")
        target_col = 'Target_Normal' if is_normal else 'Target_Runner'
        target_sym = self.symbol

        if is_normal:
            self.is_training_normal = True
        else:
            self.is_training_runner = True

        logger.info(f"Training LightGBM {mode_str.capitalize()} Mode with RLHF & PnL Feedback (Optuna Auto-Tuning) untuk {target_sym}.")

        best_params = None
        approved_ids, rejected_ids, hard_negative_ids, pnl_df = self._fetch_rlhf_pnl_data(mode=mode_str)

        # STEP 1: Multi-Regime Optuna Hyperparameter Optimization
        dm = data_miner
        if dm is None:
            try:
                from agents.data_miner import DataMinerAgent
                dm = DataMinerAgent(symbol=target_sym)
            except Exception as e:
                logger.warning(f"Tidak dapat memuat DataMinerAgent untuk Optuna multi-regime sample: {e}")

        if dm is not None:
            try:
                logger.info(f"[{mode_str.capitalize()} Mode - {target_sym}] 📦 Mengambil multi-regime sample melintasi seluruh riwayat dataset untuk Optuna...")
                sample_df = dm.load_optuna_sample(mode=mode_str, symbol=target_sym, total_sample_candles=60000)
                if not sample_df.empty and len(sample_df) >= 100:
                    logger.info(f"[{mode_str.capitalize()} Mode - {target_sym}] 🔍 Memproses indikator & filter setup Re-entry pada {len(sample_df):,} baris...")
                    sample_df = self.generate_targets(sample_df)
                    sample_df = self.add_normalized_features(sample_df)

                    sample_df = sample_df[sample_df['setup_dir'] > 0].copy() if 'setup_dir' in sample_df.columns else sample_df

                    if len(sample_df) >= 60 and len(np.unique(sample_df[target_col])) >= 2:
                        if not getattr(self, 'features', None):
                            self._extract_and_lock_features(sample_df, mode=mode_str)

                        for col in self.features:
                            if col not in sample_df.columns:
                                sample_df[col] = 0.0
                            elif not (pd.api.types.is_numeric_dtype(sample_df[col]) or pd.api.types.is_bool_dtype(sample_df[col])):
                                sample_df[col] = pd.to_numeric(sample_df[col], errors='coerce').fillna(0.0)

                        X_sample = sample_df[self.features]
                        y_sample = sample_df[target_col]
                        sw_sample = np.ones(len(sample_df), dtype=float)
                        if 'adx' in sample_df.columns:
                            if is_normal:
                                sw_sample *= np.where(sample_df['adx'] < 25.0, 1.25, 0.85)
                            else:
                                sw_sample *= np.where(sample_df['adx'] >= 25.0, 1.35, 0.75)

                        s_dir = sample_df['setup_dir'].values if 'setup_dir' in sample_df.columns else None
                        best_params = self.optimize_hyperparameters(
                            X_sample, y_sample, sw_sample, mode=mode_str, n_trials=40, setup_directions=s_dir
                        )
                    else:
                        logger.warning(f"[{mode_str.capitalize()} Mode - {target_sym}] Multi-regime sample setup Re-entry terlalu sedikit ({len(sample_df)} baris), fallback ke Chunk 1.")
            except Exception as e:
                logger.error(f"[{mode_str.capitalize()} Mode] Gagal menjalankan multi-regime Optuna pre-sampling: {e}", exc_info=True)

        # STEP 2: Ekstraksi Setup Antar-Chunk & Pelatihan Model Terpadu (Unified Fit)
        chunk_idx = 1
        all_X = []
        all_y = []
        all_sw = []
        all_sd = []

        for df in data_generator:
            if df.empty:
                continue

            logger.info(f"[{mode_str.capitalize()} Mode] Memproses Chunk {chunk_idx}/{total_chunks}...")

            is_live_feedback = '_sample_weight' in df.columns
            if is_live_feedback:
                logger.info(f"[{mode_str.capitalize()} Mode] Menginjeksi Real-Trade Live Feedback ({len(df)} sampel tertutup)...")
                sample_weights = df['_sample_weight'].to_numpy(dtype=float)
                y_target = df[target_col]
                setup_dir = df['setup_dir'].values if 'setup_dir' in df.columns else np.zeros(len(df), dtype=int)
            else:
                df = self.generate_targets(df)
                df = self.add_normalized_features(df)
                active_mask = (df['setup_dir'] > 0) if 'setup_dir' in df.columns else np.ones(len(df), dtype=bool)
                df = df[active_mask].copy()
                setup_dir = df['setup_dir'].values if 'setup_dir' in df.columns else np.zeros(len(df), dtype=int)

                if df.empty or len(df) < 20:
                    chunk_idx += 1
                    continue
                y_target = df[target_col]

            if not getattr(self, 'features', None):
                self._extract_and_lock_features(df, mode=mode_str)

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

                if 'adx' in df.columns:
                    if is_normal:
                        regime_weights = np.where(df['adx'] < 25.0, 1.25, 0.85)
                    else:
                        regime_weights = np.where(df['adx'] >= 25.0, 1.35, 0.75)
                    sample_weights *= regime_weights

            # Injeksi live trade feedback bila disematkan pada batch
            live_fb = getattr(df, 'attrs', {}).get('live_feedback')
            if live_fb is not None and not live_fb.empty:
                logger.info(f"[{mode_str.capitalize()} Mode] Menginjeksi Real-Trade Live Feedback ({len(live_fb)} sampel tertutup) ke batch data...")
                fb_df = self.add_normalized_features(live_fb.copy())
                for col in self.features:
                    if col not in fb_df.columns:
                        fb_df[col] = 0.0
                    elif not (pd.api.types.is_numeric_dtype(fb_df[col]) or pd.api.types.is_bool_dtype(fb_df[col])):
                        fb_df[col] = pd.to_numeric(fb_df[col], errors='coerce').fillna(0.0)

                if target_col in fb_df.columns:
                    X_fb = fb_df[self.features]
                    y_fb = fb_df[target_col]
                    fb_w = 2.5 if is_normal else 2.5
                    sw_fb = fb_df['_sample_weight'].to_numpy(dtype=float) if '_sample_weight' in fb_df.columns else np.ones(len(fb_df)) * fb_w
                    X = pd.concat([X, X_fb], ignore_index=True)
                    y_target = pd.concat([y_target, y_fb], ignore_index=True)
                    sample_weights = np.concatenate([sample_weights, sw_fb])

            unique_classes = np.unique(y_target)
            if len(unique_classes) >= 2 and len(X) >= 10:
                all_X.append(X)
                all_y.append(y_target)
                all_sw.append(sample_weights)
                all_sd.append(setup_dir)

            if progress_callback:
                progress_callback(chunk_idx, total_chunks)

            chunk_idx += 1
            del df, X, y_target, sample_weights
            gc.collect()

        if not all_X:
            logger.warning(f"⚠️ Batal Training ({mode_str.capitalize()} Mode): Database market_data KOSONG. Silakan tekan tombol 'Force Backfill MT5'!")
            if is_normal:
                self.is_training_normal = False
            else:
                self.is_training_runner = False
            return False

        X_full = pd.concat(all_X, ignore_index=True)
        y_full = pd.concat(all_y, ignore_index=True)
        sw_full = np.concatenate(all_sw)
        sd_full = np.concatenate(all_sd) if all_sd else None

        if best_params is None:
            logger.info(f"[{mode_str.capitalize()} Mode] Fallback: Menjalankan Optuna pada seluruh sampel multi-rezim...")
            best_params = self.optimize_hyperparameters(X_full, y_full, sw_full, mode=mode_str, n_trials=40, setup_directions=sd_full)

        params = best_params.copy() if best_params else {
            'n_estimators': 200, 'learning_rate': 0.03, 'max_depth': 4, 'num_leaves': 31,
            'min_child_samples': 50, 'subsample': 0.8, 'colsample_bytree': 0.8, 'random_state': 42
        }
        if 'optimal_threshold' in params:
            th_val = float(params.pop('optimal_threshold'))
            if is_normal:
                self.optimal_threshold_normal = th_val
            else:
                self.optimal_threshold_runner = th_val

        params.pop('entry_threshold', None)
        params['objective'] = 'binary'
        params.pop('num_class', None)
        params['verbose'] = -1
        params['random_state'] = 42
        if 'class_weight' not in params:
            params['class_weight'] = None

        logger.info(f"[{mode_str.capitalize()} Mode] 🚀 Melatih model LightGBM terpadu pada {len(X_full):,} sampel setup multi-rezim...")
        model = lgb.LGBMClassifier(**params)
        model.fit(X_full, y_full, sample_weight=sw_full)
        logger.info(f"[{mode_str.capitalize()} Mode] ✅ Model LightGBM terpadu berhasil dilatih ({model.n_estimators} pohon)!")

        cal_th = self.calibrate_optimal_threshold(
            model, X_full, y_full, mode=mode_str, setup_directions=sd_full, min_signals=25
        )

        if is_normal:
            self.model_normal = model
            self.optimal_threshold_normal = cal_th
            self.is_training_normal = False
        else:
            self.model_runner = model
            self.optimal_threshold_runner = cal_th
            self.is_training_runner = False

        self.save_models()
        return True

    def train_normal_mode(self, data_generator, total_chunks: int = 1, progress_callback=None, data_miner=None) -> bool:
        return self._execute_training_pipeline("normal", data_generator, total_chunks, progress_callback, data_miner)

    def train_runner_mode(self, data_generator, total_chunks: int = 1, progress_callback=None, data_miner=None) -> bool:
        return self._execute_training_pipeline("runner", data_generator, total_chunks, progress_callback, data_miner)

    # ---------------------------------------------------------------------------------
    # ONLINE LEARNING (Micro-Retrain)
    # ---------------------------------------------------------------------------------
    def micro_retrain(self, mode: str, df_recent: pd.DataFrame, live_feedback_df: pd.DataFrame = None) -> bool:
        """
        Online Learning (Micro-Retrain):
        Melatih incremental model secara cepat (warm-start init_model) dengan data candle terbaru
        dan live decision feedback tanpa memakan waktu Optuna.
        """
        mode_str = mode.lower()
        if mode_str == "normal":
            self.is_training_normal = True
        else:
            self.is_training_runner = True

        try:
            current_model = self.model_normal if mode_str == "normal" else self.model_runner
            if current_model is None:
                logger.warning(f"[MICRO-RETRAIN] Model {mode_str.upper()} belum pernah dilatih (None). Lakukan Full/Initial Train terlebih dahulu.")
                return False

            if df_recent is None or df_recent.empty:
                logger.warning(f"[MICRO-RETRAIN] Data candle recent kosong untuk {mode_str.upper()}.")
                return False

            df = self.generate_targets(df_recent.copy())
            df = self.add_normalized_features(df)
            active_mask = (df['setup_dir'] > 0) if 'setup_dir' in df.columns else np.ones(len(df), dtype=bool)
            df = df[active_mask].copy()

            if df.empty or len(df) < 20:
                logger.info(f"[MICRO-RETRAIN] Terlalu sedikit sampel re-entry ({len(df)}) untuk {mode_str.upper()}. Lewati.")
                return False

            target_col = 'Target_Normal' if mode_str == 'normal' else 'Target_Runner'
            y = df[target_col]

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

            if 'adx' in df.columns:
                if mode_str == 'normal':
                    sample_weights *= np.where(df['adx'] < 25.0, 1.25, 0.85)
                else:
                    sample_weights *= np.where(df['adx'] >= 25.0, 1.35, 0.75)

            if live_feedback_df is not None and not live_feedback_df.empty:
                fb_df = self.add_normalized_features(live_feedback_df.copy())
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

            unique_classes = np.unique(y)
            if len(unique_classes) < 2 or len(X) < 20:
                logger.warning(f"[MICRO-RETRAIN] Sampel atau kelas tidak lengkap ({len(X)} baris, kelas: {unique_classes}) untuk {mode_str.upper()}. Lewati.")
                return False

            current_n_est = getattr(current_model, 'n_estimators', 100) or 100
            new_n_est = current_n_est + 15
            current_model.set_params(n_estimators=new_n_est, objective='binary', verbose=-1)
            current_model.fit(X, y, sample_weight=sample_weights, init_model=current_model)

            logger.info(f"[MICRO-RETRAIN] ✅ Berhasil update model {mode_str.upper()} secara inkremental ({len(X)} sampel, total pohon: {new_n_est}).")
            self.save_models()
            return True
        except Exception as e:
            logger.error(f"[MICRO-RETRAIN] Gagal micro retrain {mode_str}: {e}")
            return False
        finally:
            if mode_str == "normal":
                self.is_training_normal = False
            else:
                self.is_training_runner = False
            gc.collect()

    # ---------------------------------------------------------------------------------
    # INFERENCE & EXPLAINABILITY (XAI)
    # ---------------------------------------------------------------------------------
    def get_top_feature_contributions(self, X_row, top_n: int = 3):
        if isinstance(X_row, pd.Series):
            X_df = self.add_normalized_features(pd.DataFrame([X_row]))
            X_row = X_df.iloc[0]
        elif isinstance(X_row, pd.DataFrame):
            X_df = self.add_normalized_features(X_row.copy())
            X_row = X_df.iloc[0]
        return get_top_feature_contributions(self.model_normal, self.features, X_row, top_n=top_n)

    def get_live_probabilities(self, X_live) -> Dict[str, float]:
        """
        Membaca skor probabilitas seketika (live) dari model yang telah dilatih
        (Digunakan untuk pemicu Dynamic Exhaustion Exit & Entry Signal).
        Mendukung Binary Meta-Model (evaluasi setup arah teknis + peluang menang).
        """
        empty_res = {"normal_buy": 0.0, "normal_sell": 0.0, "runner_buy": 0.0, "runner_sell": 0.0, "normal": 0.0, "runner": 0.0}
        if self.model_normal is None and self.model_runner is None:
            return empty_res

        if isinstance(X_live, pd.Series):
            X_live = pd.DataFrame([X_live])
        else:
            X_live = X_live.copy()

        X_live = self.add_normalized_features(X_live)

        valid_cols = [c for c in self.features if c in X_live.columns]
        if not valid_cols:
            return empty_res

        try:
            X_eval = X_live[valid_cols].copy()
            for c in valid_cols:
                if not (pd.api.types.is_numeric_dtype(X_eval[c]) or pd.api.types.is_bool_dtype(X_eval[c])):
                    X_eval[c] = pd.to_numeric(X_eval[c], errors='coerce').fillna(0.0)
            pn_buy, pn_sell = 0.0, 0.0
            pr_buy, pr_sell = 0.0, 0.0

            s_dir = int(X_live['setup_dir'].iloc[0]) if 'setup_dir' in X_live.columns else 0
            is_valid_buy = (s_dir == 1)
            is_valid_sell = (s_dir == 2)

            if self.model_normal is not None:
                probs_n = self.model_normal.predict_proba(X_eval)[0]
                classes_n = list(getattr(self.model_normal, 'classes_', [0, 1]))
                idx_w = classes_n.index(1) if 1 in classes_n else 1
                p_win = float(probs_n[idx_w]) if len(probs_n) > idx_w else float(probs_n[-1])
                if is_valid_buy:
                    pn_buy = p_win
                elif is_valid_sell:
                    pn_sell = p_win

            if self.model_runner is not None:
                probs_r = self.model_runner.predict_proba(X_eval)[0]
                classes_r = list(getattr(self.model_runner, 'classes_', [0, 1]))
                idx_w = classes_r.index(1) if 1 in classes_r else 1
                p_win = float(probs_r[idx_w]) if len(probs_r) > idx_w else float(probs_r[-1])
                if is_valid_buy:
                    pr_buy = p_win
                elif is_valid_sell:
                    pr_sell = p_win

            return {
                "normal_buy": pn_buy,
                "normal_sell": pn_sell,
                "runner_buy": pr_buy,
                "runner_sell": pr_sell,
                "normal": max(pn_buy, pn_sell),
                "runner": max(pr_buy, pr_sell)
            }
        except Exception as e:
            logger.debug(f"Gagal kalkulasi live probabilities: {e}")
            return empty_res
