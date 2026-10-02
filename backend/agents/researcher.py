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
    get_profile,
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
        self.profile = get_profile(self.symbol)
        self.model_unified = None
        self.model_normal = None
        self.model_runner = None
        self.active_timeframe = "M5"
        self.features: List[str] = []
        self.is_training_normal = False
        self.is_training_runner = False
        self.last_accuracy_normal = 0.0
        self.last_accuracy_runner = 0.0
        self.last_trained_normal = None
        self.last_trained_runner = None
        self.optimal_threshold_normal = 0.54
        self.optimal_threshold_runner = 0.54
        self.max_runner_rr = getattr(self.profile, "rr_runner", 3.5)
        self.pending_training: Dict[str, Dict[str, Any]] = {}
        self._current_train_type: str = "incremental"
        self._models_cache: Dict[str, Dict[str, Any]] = {}

    def set_symbol(self, symbol: str):
        clean_sym = str(symbol or "XAUUSD").upper()
        if self.symbol == clean_sym and (self.model_unified is not None or self.model_normal is not None):
            return

        if self.symbol:
            self._models_cache[self.symbol] = {
                "unified": self.model_unified,
                "normal": self.model_normal,
                "runner": self.model_runner,
                "active_timeframe": self.active_timeframe,
                "features": self.features,
                "last_accuracy_normal": self.last_accuracy_normal,
                "last_accuracy_runner": self.last_accuracy_runner,
                "last_trained_normal": self.last_trained_normal,
                "last_trained_runner": self.last_trained_runner,
                "optimal_threshold_normal": self.optimal_threshold_normal,
                "optimal_threshold_runner": self.optimal_threshold_runner,
                "max_runner_rr": self.max_runner_rr,
                "oos_scorecard": getattr(self, "oos_scorecard", {"normal": None, "runner": None})
            }

        self.symbol = clean_sym
        self.profile = get_profile(self.symbol)
        self.max_runner_rr = getattr(self.profile, "rr_runner", 3.5)

        if clean_sym in self._models_cache:
            c = self._models_cache[clean_sym]
            self.model_unified = c.get("unified")
            self.model_normal = c.get("normal", self.model_unified)
            self.model_runner = c.get("runner", self.model_unified)
            self.active_timeframe = c.get("active_timeframe", "M5")
            self.features = c.get("features", [])
            self.last_accuracy_normal = c["last_accuracy_normal"]
            self.last_accuracy_runner = c["last_accuracy_runner"]
            self.last_trained_normal = c["last_trained_normal"]
            self.last_trained_runner = c["last_trained_runner"]
            self.optimal_threshold_normal = c.get("optimal_threshold_normal", 0.54)
            self.optimal_threshold_runner = c.get("optimal_threshold_runner", 0.54)
            self.max_runner_rr = c["max_runner_rr"]
            self.oos_scorecard = c.get("oos_scorecard", {"normal": None, "runner": None})
        else:
            self.model_unified = None
            self.model_normal = None
            self.model_runner = None
            self.active_timeframe = "M5"
            self.features = []
            self.last_accuracy_normal = 0.0
            self.last_accuracy_runner = 0.0
            self.last_trained_normal = None
            self.last_trained_runner = None
            self.optimal_threshold_normal = 0.54
            self.optimal_threshold_runner = 0.54
            self.oos_scorecard = {"normal": None, "runner": None}
            self.load_models()

        self.pending_training = {}
        for m in ["unified", "normal", "runner"]:
            p_info = ModelManager.get_pending_info(self.symbol, m)
            if p_info:
                p_model = ModelManager.load_pending_model(self.symbol, m)
                if p_model is not None:
                    self.pending_training[m] = {"model": p_model, "info": p_info}

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
            normal_trained=(self.model_unified is not None or self.model_normal is not None),
            runner_acc=self.last_accuracy_runner,
            runner_trained_at=self.last_trained_runner,
            runner_th=self.optimal_threshold_runner,
            runner_trained=(self.model_unified is not None or self.model_runner is not None),
            max_runner_rr=self.max_runner_rr,
            normal_oos_scorecard=self.oos_scorecard.get("normal") if getattr(self, "oos_scorecard", None) else None,
            runner_oos_scorecard=self.oos_scorecard.get("runner") if getattr(self, "oos_scorecard", None) else None
        )

    def save_models(self):
        return ModelManager.save_models(
            symbol=self.symbol,
            model_normal=self.model_normal or self.model_unified,
            model_runner=self.model_runner or self.model_unified,
            normal_acc=self.last_accuracy_normal,
            normal_trained_at=self.last_trained_normal,
            normal_th=self.optimal_threshold_normal,
            runner_acc=self.last_accuracy_runner,
            runner_trained_at=self.last_trained_runner,
            runner_th=self.optimal_threshold_runner,
            max_runner_rr=self.max_runner_rr,
            normal_oos_scorecard=self.oos_scorecard.get("normal") if getattr(self, "oos_scorecard", None) else None,
            runner_oos_scorecard=self.oos_scorecard.get("runner") if getattr(self, "oos_scorecard", None) else None
        )

    def load_models(self) -> bool:
        loaded = ModelManager.load_models(self.symbol)
        if loaded.get("loaded", False):
            self.model_unified = loaded.get("model_unified")
            self.model_normal = loaded.get("model_normal") or self.model_unified
            self.model_runner = loaded.get("model_runner") or self.model_unified
            self.active_timeframe = loaded.get("timeframe", "M5")
            self.features = loaded.get("features", [])
            self.last_accuracy_normal = loaded.get("last_accuracy_normal", 0.0)
            self.last_trained_normal = loaded.get("last_trained_normal")
            self.optimal_threshold_normal = loaded.get("optimal_threshold_normal", 0.50)
            self.last_accuracy_runner = loaded.get("last_accuracy_runner", 0.0)
            self.last_trained_runner = loaded.get("last_trained_runner")
            self.optimal_threshold_runner = loaded.get("optimal_threshold_runner", 0.50)
            self.oos_scorecard = loaded.get("oos_scorecard", {"normal": None, "runner": None})
            self.max_runner_rr = loaded.get("max_runner_rr", 3.5)
            return True
        return False

    # ---------------------------------------------------------------------------------
    # RESEARCH HELPERS (Delegates to Submodules)
    # ---------------------------------------------------------------------------------
    def generate_targets(self, df: pd.DataFrame, symbol: str = None, **kwargs) -> pd.DataFrame:
        target_sym = symbol or self.symbol
        return generate_targets(df, max_runner_rr=getattr(self, 'max_runner_rr', 5.0), symbol=target_sym, **kwargs)

    def add_normalized_features(self, df: pd.DataFrame) -> pd.DataFrame:
        return add_normalized_features(df)

    def _extract_and_lock_features(self, df: pd.DataFrame, mode: str = "normal") -> List[str]:
        self.features = extract_and_lock_features(df, mode=mode)
        return self.features

    def get_model_features(self, model: Any = None, mode: str = "normal") -> List[str]:
        target_model = model or (self.model_normal if mode == "normal" else self.model_runner)
        if target_model is not None:
            if hasattr(target_model, 'feature_name_') and target_model.feature_name_ is not None:
                return list(target_model.feature_name_)
            if hasattr(target_model, 'booster_') and hasattr(target_model.booster_, 'feature_name'):
                return list(target_model.booster_.feature_name())
        if self.features:
            return list(self.features)
        return []

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
            max_runner_rr=getattr(self, 'max_runner_rr', 5.0),
            symbol=self.symbol
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

    def _execute_training_pipeline(
        self,
        mode: str = "unified",
        *args,
        **kwargs
    ) -> bool:
        """Legacy dual-model training pipeline deprecated. Forwards to train_pair_model."""
        res = self.train_pair_model(symbol=self.symbol)
        return res.get("success", False) if isinstance(res, dict) else bool(res)


    def apply_pending_model(self, mode: str) -> tuple:
        mode_str = mode.lower()
        pending = self.pending_training.get(mode_str)
        if not pending and mode_str in ("normal", "unified"):
            alt_mode = "unified" if mode_str == "normal" else "normal"
            pending = self.pending_training.get(alt_mode)

        if not pending:
            for m in [mode_str, "unified", "normal"]:
                info = ModelManager.get_pending_info(self.symbol, m)
                p_model = ModelManager.load_pending_model(self.symbol, m)
                if info and p_model is not None:
                    pending = {"model": p_model, "info": info}
                    break

        if not pending:
            return False, f"Tidak ada model pending untuk {self.symbol} mode {mode_str}.", {}

        model = pending["model"]
        info = pending["info"]
        cal_th = info.get("calibrated_threshold", 0.50)
        new_acc = info.get("new_accuracy", 0.0)
        trained_at = info.get("trained_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        oos_report = info.get("oos_report", {})
        timeframe = info.get("timeframe", getattr(self, "active_timeframe", "M5"))

        self.model_unified = model
        self.model_normal = model
        self.model_runner = model
        self.optimal_threshold_normal = cal_th
        self.optimal_threshold_runner = cal_th
        self.last_accuracy_normal = new_acc
        self.last_accuracy_runner = new_acc
        self.last_trained_normal = trained_at
        self.last_trained_runner = trained_at
        self.active_timeframe = timeframe

        if not getattr(self, "oos_scorecard", None):
            self.oos_scorecard = {}
        if oos_report:
            self.oos_scorecard[mode_str] = oos_report
            self.oos_scorecard["unified"] = oos_report
            self.oos_scorecard["normal"] = oos_report

        ModelManager.save_unified_model(
            symbol=self.symbol,
            model=model,
            features=info.get("features", self.features),
            timeframe=timeframe,
            win_rate=new_acc * 100.0 if new_acc <= 1.0 else new_acc,
            profit_factor=info.get("profit_factor", 1.0),
            optimal_threshold=cal_th,
            oos_scorecard=oos_report,
            extra_meta={"timeframe_benchmark": info.get("timeframe_benchmark", {})}
        )

        if oos_report:
            try:
                from database import save_scorecard_record
                save_scorecard_record(oos_report)
            except Exception as e_db:
                logger.warning(f"Gagal mencatat scorecard ke database: {e_db}")

        for m_clean in set([mode_str, "unified", "normal", "runner"]):
            ModelManager.discard_pending_model(self.symbol, m_clean)
            self.pending_training.pop(m_clean, None)

        if self.symbol in self._models_cache:
            self._models_cache[self.symbol]["unified"] = model
            self._models_cache[self.symbol]["normal"] = model
            self._models_cache[self.symbol]["runner"] = model
            self._models_cache[self.symbol]["active_timeframe"] = timeframe

        logger.info(f"✅ [{self.symbol}] Model diterapkan sebagai model.pkl tunggal (TF: {timeframe}).")
        return True, f"Model {mode_str.upper()} ({self.symbol}) berhasil disimpan.", info

    def micro_retrain(
        self,
        mode: str = "normal",
        df_recent: Optional[pd.DataFrame] = None,
        feedback_df: Optional[pd.DataFrame] = None,
        symbol: Optional[str] = None
    ) -> bool:
        target_sym = str(symbol or self.symbol).upper()
        if self.symbol != target_sym:
            self.set_symbol(target_sym)

        curr_model = self.model_unified or (self.model_normal if mode == "normal" else self.model_runner)
        if curr_model is None:
            self.load_models()
            curr_model = self.model_unified or (self.model_normal if mode == "normal" else self.model_runner)

        if curr_model is None:
            logger.warning(f"[MICRO-RETRAIN] Model belum tersedia untuk {target_sym}.")
            return False

        if df_recent is None or df_recent.empty or len(df_recent) < 50:
            return False

        df_proc = self.generate_targets(df_recent, symbol=target_sym)
        if df_proc is None or df_proc.empty:
            return False

        features = self.get_model_features(curr_model, mode=mode)
        if not features:
            features = [c for c in df_proc.columns if c not in (
                'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'real_volume',
                'Target_Class', 'Target_Buy', 'Target_Sell', 'Target_Normal', 'Target_Runner',
                '_sample_weight', 'target', 'forward_mfe_r'
            )]
            self.features = features

        X = df_proc.reindex(columns=features, fill_value=0.0).copy()
        for col in features:
            if not (pd.api.types.is_numeric_dtype(X[col]) or pd.api.types.is_bool_dtype(X[col])):
                X[col] = pd.to_numeric(X[col], errors='coerce').fillna(0.0)

        is_multiclass = 'Target_Class' in df_proc.columns
        if is_multiclass:
            y = df_proc['Target_Class'].values
        elif 'Target_Normal' in df_proc.columns:
            y = df_proc['Target_Normal'].values
        else:
            return False

        sample_weights = np.linspace(0.8, 1.2, len(y), dtype=np.float32)

        if feedback_df is not None and not feedback_df.empty:
            target_col = 'Target_Class' if is_multiclass and 'Target_Class' in feedback_df.columns else ('Target_Normal' if 'Target_Normal' in feedback_df.columns else None)
            if target_col:
                X_fb = feedback_df.reindex(columns=features, fill_value=0.0).copy()
                for col in features:
                    if not (pd.api.types.is_numeric_dtype(X_fb[col]) or pd.api.types.is_bool_dtype(X_fb[col])):
                        X_fb[col] = pd.to_numeric(X_fb[col], errors='coerce').fillna(0.0)
                y_fb = feedback_df[target_col].values
                sw_fb = np.full(len(y_fb), 2.0, dtype=np.float32)
                X = pd.concat([X, X_fb], ignore_index=True)
                y = np.concatenate([y, y_fb])
                sample_weights = np.concatenate([sample_weights, sw_fb])

        if len(np.unique(y)) < 2:
            return False

        params = curr_model.get_params() if hasattr(curr_model, 'get_params') else {}
        params['n_estimators'] = min(300, getattr(curr_model, 'n_estimators', 100) + 15)
        params['learning_rate'] = min(0.05, getattr(curr_model, 'learning_rate', 0.03))
        params['verbose'] = -1
        params['random_state'] = 42
        if is_multiclass:
            params['objective'] = 'multiclass'
            params['num_class'] = 3
        else:
            params['objective'] = 'binary'
            params.pop('num_class', None)

        new_model = lgb.LGBMClassifier(**params)
        booster_init = getattr(curr_model, 'booster_', None) or (curr_model if isinstance(curr_model, lgb.Booster) else None)
        new_model.fit(X, y, sample_weight=sample_weights, init_model=booster_init)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.model_unified = new_model
        self.model_normal = new_model
        self.model_runner = new_model
        self.last_trained_normal = now_str
        self.last_trained_runner = now_str

        ModelManager.save_unified_model(
            symbol=target_sym,
            model=new_model,
            features=features,
            timeframe=getattr(self, 'active_timeframe', 'M5'),
            win_rate=self.last_accuracy_normal * 100.0,
            optimal_threshold=self.optimal_threshold_normal,
            oos_scorecard=getattr(self, 'oos_scorecard', {}).get(mode)
        )

        if target_sym in self._models_cache:
            self._models_cache[target_sym]["unified"] = new_model
            self._models_cache[target_sym]["normal"] = new_model
            self._models_cache[target_sym]["runner"] = new_model
            self._models_cache[target_sym]["last_trained_normal"] = now_str

        logger.info(f"✨ [MICRO-RETRAIN - {target_sym}] Model berhasil diperbarui secara incremental ({new_model.n_estimators} trees).")
        return True

    def discard_pending_model(self, mode: str) -> tuple:
        """
        User menolak / membatalkan dialog simpan di UI:
        Membuang checkpoint pending tanpa menyentuh file .pkl lama.
        """
        mode_str = mode.lower()
        ModelManager.discard_pending_model(self.symbol, mode_str)
        if mode_str == "unified":
            ModelManager.discard_pending_model(self.symbol, "normal")
            self.pending_training.pop("normal", None)
        self.pending_training.pop(mode_str, None)
        logger.info(f"🗑️ [{mode_str.capitalize()} Mode - {self.symbol}] Model pending dibuang. Model .pkl lama tetap dipertahankan.")
        return True, f"Model baru {mode_str.upper()} ({self.symbol}) dibuang. Model lama tetap aktif."
    def train_pair_model(
        self,
        symbol: str = None,
        auto_discover_tf: bool = True,
        timeframe: str = None,
        data_miner = None,
        progress_callback = None,
        force_rebuild: bool = False
    ) -> Dict[str, Any]:
    
        target_sym = str(symbol or self.symbol).upper()
        self.set_symbol(target_sym)
        self.is_training_normal = True
        self.is_training_runner = True

        try:
            if data_miner is None:
                from agents.data_miner import DataMinerAgent
                data_miner = DataMinerAgent(symbol=target_sym)

            from database import get_db_size, sync_engine
            db_count = get_db_size(target_sym)
            existing_tf = data_miner.get_pair_timeframe() if data_miner else "M15"
            tf_benchmark = {}

            # 1. Timeframe Discovery (Otomatis Database-First di RAM jika diminta)
            if auto_discover_tf or not timeframe:
                from agents.research.timeframe_finder import discover_best_timeframe
                if progress_callback:
                    progress_callback(1, 5)
                logger.info(f"🔎 [TF DISCOVERY] Menjalankan benchmark timeframe optimal dari database lokal untuk {target_sym}...")
                disc_res = discover_best_timeframe(target_sym, candidate_tfs=["M5", "M7", "M15", "M35", "H1", "H2"])
                chosen_tf = disc_res.get("best_timeframe", existing_tf or "M15")
                tf_benchmark = disc_res.get("results", {})
            else:
                chosen_tf = timeframe or existing_tf or "M15"

            self.active_timeframe = chosen_tf
            use_local_db = (db_count >= 500) and (not force_rebuild)

            if use_local_db:
                logger.info(f"⚡ [DATABASE-MAXIMIZE] Memuat seluruh {db_count:,} candle dari PostgreSQL lokal ({target_sym})...")

                # Micro-sync cepat hanya untuk candle baru terakhir jika MT5 online
                try:
                    data_miner.sync_latest_data()
                except Exception as e_sync:
                    logger.warning(f"Micro-sync candle baru dilewati: {e_sync}")

                query = f'SELECT * FROM "{data_miner.table_name}" ORDER BY "time" ASC'
                chunk_list = []
                for chunk in pd.read_sql(query, con=sync_engine, chunksize=50000):
                    if 'time' in chunk.columns:
                        chunk['time'] = pd.to_datetime(chunk['time'])
                    chunk_list.append(chunk)

                df_raw = pd.concat(chunk_list, ignore_index=True) if chunk_list else pd.DataFrame()
                if 'time' in df_raw.columns:
                    df_raw.set_index('time', inplace=True)
                del chunk_list
                gc.collect()

                # Deteksi otomatis apakah dataset database berupa M1 Atom (rentang < 120 detik per bar)
                is_m1_dataset = False
                if len(df_raw) >= 5:
                    sample_diff = (df_raw.index[1:5] - df_raw.index[0:4]).total_seconds().median()
                    is_m1_dataset = bool(sample_diff <= 120)

                if is_m1_dataset and chosen_tf.upper() != "M1":
                    logger.info(f"🔄 [M1 VECTOR RESAMPLING] Meresample {len(df_raw):,} candle M1 (2014-2026) menjadi {chosen_tf} di RAM...")
                    from agents.research.timeframe_finder import resample_m1_df
                    df = resample_m1_df(df_raw, chosen_tf)
                    from utils.indicators import calculate_bbma
                    df = calculate_bbma(df)
                    del df_raw
                    gc.collect()
                    logger.info(f"✅ Selesai resample ke {chosen_tf}. Total bar latih: {len(df):,} candle.")
                else:
                    df = df_raw
                    # Batas aman untuk M1 murni agar tidak kehabisan RAM (gunakan 500k candle terakhir ~2 tahun)
                    if chosen_tf.upper() == "M1" and len(df) > 500000:
                        logger.info(f"⚡ [M1 SLICE] Membatasi 500,000 candle M1 terakhir dari {len(df):,} untuk efisiensi memori.")
                        df = df.iloc[-500000:].copy()
                    if 'sma_20' not in df.columns:
                        from utils.indicators import calculate_bbma
                        df = calculate_bbma(df)
            else:
                # Cold Start (Database Kosong < 500 bar)
                logger.info(f"🚀 [MT5 COLD-START] Menarik data bersih {chosen_tf} dari MT5 untuk {target_sym}...")
                if progress_callback:
                    progress_callback(2, 5)

                df = data_miner.fetch_and_calculate_bbma(n_candles=30000, start_pos=0, timeframe=chosen_tf)
                if df is None or len(df) < 500:
                    logger.error(f"Data tidak mencukupi untuk melatih {target_sym} di {chosen_tf}.")
                    return {"success": False, "message": f"Data tidak mencukupi ({len(df) if df is not None else 0})"}

                try:
                    data_miner._save_market_data(df, if_exists='append')
                except Exception as e_db:
                    logger.warning(f"Gagal simpan ke DB: {e_db}")

            if progress_callback:
                progress_callback(3, 5)

            # Ekstraksi fitur dan target murni forward profit
            logger.info(f"📊 Menghitung target Triple Barrier dan fitur normalisasi untuk {len(df):,} candle ({target_sym} {chosen_tf})...")
            df = self.generate_targets(df, tp_mult=1.5, sl_mult=1.0, horizon=36, symbol=target_sym)
            df = self.add_normalized_features(df)
            self._extract_and_lock_features(df, mode="unified")

            for col in self.features:
                if col not in df.columns:
                    df[col] = 0.0
                else:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

            X = df[self.features].copy()
            y = df['Target_Class'].copy()

            # Train / Test split (80% / 20%) dengan Purged Embargo
            horizon = 36
            split_idx = int(len(X) * 0.80)
            train_end_idx = max(50, split_idx - horizon)
            X_train, y_train = X.iloc[:train_end_idx], y.iloc[:train_end_idx]
            X_test, y_test = X.iloc[split_idx:], y.iloc[split_idx:]

            # TD-07 & TD-08: Tri-Factor Weighting (Balanced Class * Sample Uniqueness * Linear Recency * Cost-Sensitive Bonus)
            from sklearn.utils.class_weight import compute_sample_weight
            from agents.research.target_labeler import compute_sample_uniqueness
            cw = compute_sample_weight('balanced', y_train)
            uniqueness = compute_sample_uniqueness(len(y_train), horizon=36)
            recency = np.linspace(0.85, 1.15, len(y_train), dtype=np.float32)
            directional_bonus = np.where(y_train != 0, 1.25, 0.85)
            sw_train = cw * uniqueness * recency * directional_bonus
            sw_train = sw_train / max(1e-4, float(np.mean(sw_train)))

            if progress_callback:
                progress_callback(4, 5)

            # Optuna Multiclass Tuning (25 Trials) dengan Tri-Factor Sample Weights & Asymmetric Penalties
            best_opt = {}
            try:
                from agents.research.optimizer import optimize_unified_multiclass
                best_opt = optimize_unified_multiclass(X_train, y_train, sample_weights=sw_train, n_trials=25, symbol=target_sym)
            except Exception as e_opt:
                logger.warning(f"Optuna tuning error, fallback ke default params: {e_opt}")

            threshold = float(best_opt.get('optimal_threshold', 0.45))
            lgb_params = {
                'n_estimators': best_opt.get('n_estimators', 150),
                'learning_rate': best_opt.get('learning_rate', 0.03),
                'max_depth': best_opt.get('max_depth', 4),
                'num_leaves': best_opt.get('num_leaves', 25),
                'min_child_samples': best_opt.get('min_child_samples', 30),
                'subsample': best_opt.get('subsample', 0.8),
                'colsample_bytree': best_opt.get('colsample_bytree', 0.8),
                'reg_alpha': best_opt.get('reg_alpha', 0.1),
                'reg_lambda': best_opt.get('reg_lambda', 0.1),
                'objective': 'multiclass',
                'num_class': 3,
                'random_state': 42,
                'verbose': -1,
                'n_jobs': -1
            }
            model = lgb.LGBMClassifier(**lgb_params)
            model.fit(X_train, y_train, sample_weight=sw_train)

            # Kalibrasi presisi threshold optimal post-training
            try:
                from agents.research.calibrator import calibrate_optimal_threshold
                cal_th = calibrate_optimal_threshold(model, X_train, y_train, mode="unified", symbol=target_sym)
                if cal_th and cal_th > 0.35:
                    threshold = float(cal_th)
            except Exception as e_cal:
                logger.debug(f"Dynamic calibration fallback: {e_cal}")

            # Validasi OOS dengan Position Holding State Machine
            probs = model.predict_proba(X_test)
            classes = list(getattr(model, 'classes_', [0, 1, 2]))
            idx_buy = classes.index(1) if 1 in classes else -1
            idx_sell = classes.index(2) if 2 in classes else -1

            p_buy = probs[:, idx_buy] if idx_buy >= 0 else np.zeros(len(X_test))
            p_sell = probs[:, idx_sell] if idx_sell >= 0 else np.zeros(len(X_test))

            buy_sig = (p_buy >= threshold) & (p_buy > p_sell)
            sell_sig = (p_sell >= threshold) & (p_sell > p_buy)

            wins = 0
            losses = 0
            gross_p = 0.0
            gross_l = 0.0
            y_test_v = y_test.values

            cooldown_bars = 4
            cooldown_counter = 0

            for idx in range(len(y_test_v)):
                if cooldown_counter > 0:
                    cooldown_counter -= 1
                    continue

                act = y_test_v[idx]
                if buy_sig[idx]:
                    if act == 1:
                        wins += 1
                        gross_p += 1.5
                    elif act == 0 or act == 2:
                        losses += 1
                        gross_l += 1.0
                    cooldown_counter = cooldown_bars
                elif sell_sig[idx]:
                    if act == 2:
                        wins += 1
                        gross_p += 1.5
                    elif act == 0 or act == 1:
                        losses += 1
                        gross_l += 1.0
                    cooldown_counter = cooldown_bars

            total_trades = wins + losses
            wr = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
            pf = (gross_p / max(1e-4, gross_l)) if total_trades > 0 else 0.0

            # Evaluasi Kriteria OOS Gate
            passed_oos = bool(pf >= 1.25 and wr >= 50.0)
            old_wr = float(self.last_accuracy_normal or 0.0)

            oos_report = {
                "symbol": target_sym,
                "timeframe": chosen_tf,
                "total_trades": total_trades,
                "win_rate": round(wr, 2),
                "profit_factor": round(pf, 2),
                "evaluated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            pending_info = {
                "symbol": target_sym,
                "mode": "unified",
                "train_type": "full" if auto_discover_tf else "incremental",
                "calibrated_threshold": threshold,
                "features": self.features,
                "passed_oos": passed_oos,
                "new_accuracy": round(wr / 100.0, 4),
                "old_accuracy": round(old_wr, 4),
                "profit_factor": round(pf, 2),
                "expectancy": round((gross_p - gross_l) / max(1, total_trades), 2),
                "max_drawdown": 0.0,
                "total_trades": total_trades,
                "timeframe": chosen_tf,
                "reasons": [
                    f"Win Rate OOS: {wr:.1f}% (PF: {pf:.2f}) pada timeframe {chosen_tf}.",
                    f"Threshold entry optimal dikalibrasi ke {threshold*100:.1f}%."
                ],
                "trained_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "timeframe_benchmark": tf_benchmark,
                "oos_report": oos_report
            }

            # Simpan sebagai PENDING (TIDAK MENIMPA model.pkl LAMA)
            ModelManager.save_pending_model(target_sym, "unified", model, pending_info)
            ModelManager.save_pending_model(target_sym, "normal", model, pending_info)
            self.pending_training["unified"] = {"model": model, "info": pending_info}
            self.pending_training["normal"] = {"model": model, "info": pending_info}

            if progress_callback:
                progress_callback(5, 5)

            logger.info(
                f"⏸️ [TRAIN PAIR MODEL SELESAI] Model kandidat baru {target_sym} ({chosen_tf}) "
                f"berhasil dilatih (WR: {wr:.1f}%, PF: {pf:.2f}, Lolos OOS: {passed_oos}). "
                f"Disimpan sebagai PENDING — Menunggu konfirmasi persetujuan user di UI!"
            )
            return {
                "success": True,
                "symbol": target_sym,
                "timeframe": chosen_tf,
                "win_rate": wr,
                "profit_factor": pf,
                "total_trades": total_trades,
                "timeframe_benchmark": tf_benchmark
            }
        except Exception as e:
            logger.error(f"Gagal melatih model tunggal {target_sym}: {e}", exc_info=True)
            return {"success": False, "message": str(e)}
        finally:
            self.is_training_normal = False
            self.is_training_runner = False
            gc.collect()

    def train_normal_mode(self, data_generator=None, total_chunks: int = 1, progress_callback=None, data_miner=None, train_type: str = None) -> bool:
        res = self.train_pair_model(symbol=self.symbol, data_miner=data_miner, progress_callback=progress_callback)
        return res.get("success", False) if isinstance(res, dict) else bool(res)

    def train_runner_mode(self, data_generator=None, total_chunks: int = 1, progress_callback=None, data_miner=None, train_type: str = None) -> bool:
        res = self.train_pair_model(symbol=self.symbol, data_miner=data_miner, progress_callback=progress_callback)
        return res.get("success", False) if isinstance(res, dict) else bool(res)

    def get_live_probabilities(self, X_live) -> Dict[str, float]:
        """
        Membaca skor probabilitas seketika (live) dari 1 model tunggal per pair.
        Probabilitas Buy, Sell, dan Netral dihitung dari jarak BBMA murni.
        """
        empty_res = {
            "buy": 0.0, "sell": 0.0, "neutral": 0.0, "probability": 0.0,
            "normal_buy": 0.0, "normal_sell": 0.0, "runner_buy": 0.0, "runner_sell": 0.0,
            "normal": 0.0, "runner": 0.0
        }
        active_model = getattr(self, 'model_unified', None) or self.model_normal or self.model_runner
        if active_model is None:
            return empty_res

        if isinstance(X_live, pd.Series):
            X_live = pd.DataFrame([X_live])
        else:
            X_live = X_live.copy()

        # Hitung feature engineering pada buffer historis untuk menjaga akurasi rolling, shift, dan slope
        X_live = self.add_normalized_features(X_live)

        if not getattr(self, 'features', None):
            if hasattr(active_model, 'feature_name_'):
                self.features = list(active_model.feature_name_)
            elif hasattr(active_model, 'booster_'):
                self.features = list(active_model.booster_.feature_name())

        # Sanitasi ketat: eliminasi kolom target/mfe/forward jika ada yang tertinggal di self.features
        self.features = [
            f for f in self.features 
            if not any(kw in f.lower() for kw in ['target', 'mfe', 'forward', 'future', 'pnl', 'profit', 'horizon'])
        ]

        if not getattr(self, 'features', None):
            return empty_res

        try:
            for c in self.features:
                if c not in X_live.columns:
                    X_live[c] = 0.0
                elif not (pd.api.types.is_numeric_dtype(X_live[c]) or pd.api.types.is_bool_dtype(X_live[c])):
                    X_live[c] = pd.to_numeric(X_live[c], errors='coerce').fillna(0.0)

            # Ambil baris candle paling akhir setelah seluruh series historis dihitung
            X_eval = X_live[self.features].iloc[[-1]].copy()
            probs = active_model.predict_proba(X_eval)[0]
            classes = list(getattr(active_model, 'classes_', [0, 1, 2]))

            p_neutral = 0.0
            p_buy = 0.0
            p_sell = 0.0

            if len(classes) == 3:
                # Multiclass: 0=Neutral, 1=Buy, 2=Sell
                idx_0 = classes.index(0) if 0 in classes else -1
                idx_1 = classes.index(1) if 1 in classes else -1
                idx_2 = classes.index(2) if 2 in classes else -1
                p_neutral = float(probs[idx_0]) if idx_0 >= 0 and idx_0 < len(probs) else 0.0
                p_buy = float(probs[idx_1]) if idx_1 >= 0 and idx_1 < len(probs) else 0.0
                p_sell = float(probs[idx_2]) if idx_2 >= 0 and idx_2 < len(probs) else 0.0
            elif len(classes) == 2:
                # Binary fallback: 0=Loss, 1=Profit
                idx_1 = classes.index(1) if 1 in classes else 1
                p_val = float(probs[idx_1]) if idx_1 < len(probs) else float(probs[-1])
                is_bullish = float(X_live.get('feat_is_bullish', pd.Series([1.0])).iloc[-1]) >= 0
                if is_bullish:
                    p_buy = p_val
                else:
                    p_sell = p_val

            best_p = max(p_buy, p_sell)
            return {
                "buy": round(p_buy, 4),
                "sell": round(p_sell, 4),
                "neutral": round(p_neutral, 4),
                "probability": round(best_p, 4),
                "normal_buy": round(p_buy, 4),
                "normal_sell": round(p_sell, 4),
                "runner_buy": round(p_buy, 4),
                "runner_sell": round(p_sell, 4),
                "normal": round(best_p, 4),
                "runner": round(best_p, 4)
            }
        except Exception as e:
            logger.debug(f"Gagal kalkulasi live probabilities: {e}")
            return empty_res
