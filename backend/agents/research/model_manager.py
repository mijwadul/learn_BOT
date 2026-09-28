import os
import json
import logging
import joblib
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ModelManager:
    """
    Submodul Persistence & Checkpoint Management untuk ResearcherAgent.
    Mengatur penyimpanan, pemuatan, dan metadata model per symbol.
    """

    @staticmethod
    def get_model_dir(symbol: str) -> str:
        sym = str(symbol or "XAUUSD").upper()
        d = os.path.join("models", sym)
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def get_model_path(symbol: str, mode: str) -> str:
        d = ModelManager.get_model_dir(symbol)
        return os.path.join(d, f"model_{mode}.pkl")

    @staticmethod
    def get_metadata_path(symbol: str) -> str:
        d = ModelManager.get_model_dir(symbol)
        return os.path.join(d, "models_metadata.json")

    @staticmethod
    def save_metadata(
        symbol: str,
        normal_acc: float = 0.0,
        normal_trained_at: Optional[str] = None,
        normal_th: float = 0.54,
        normal_trained: bool = False,
        runner_acc: float = 0.0,
        runner_trained_at: Optional[str] = None,
        runner_th: float = 0.54,
        runner_trained: bool = False,
        max_runner_rr: float = 5.0,
        normal_oos_scorecard: Optional[Dict[str, Any]] = None,
        runner_oos_scorecard: Optional[Dict[str, Any]] = None
    ) -> bool:
        try:
            sym = str(symbol or "XAUUSD").upper()
            meta_path = ModelManager.get_metadata_path(sym)
            existing = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r") as f:
                        existing = json.load(f)
                except Exception:
                    existing = {}

            normal_card = normal_oos_scorecard if normal_oos_scorecard is not None else existing.get("normal", {}).get("oos_scorecard")
            runner_card = runner_oos_scorecard if runner_oos_scorecard is not None else existing.get("runner", {}).get("oos_scorecard")

            meta = {
                "symbol": sym,
                "normal": {
                    "last_accuracy": float(normal_acc),
                    "last_trained_at": normal_trained_at,
                    "trained": bool(normal_trained),
                    "optimal_threshold": float(normal_th),
                    "oos_scorecard": normal_card
                },
                "runner": {
                    "last_accuracy": float(runner_acc),
                    "last_trained_at": runner_trained_at,
                    "trained": bool(runner_trained),
                    "max_runner_rr": float(max_runner_rr),
                    "optimal_threshold": float(runner_th),
                    "oos_scorecard": runner_card
                },
                "oos_scorecard": {
                    "normal": normal_card,
                    "runner": runner_card
                }
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
            logger.info(
                f"[RESEARCHER-{sym}] Metadata akurasi tersimpan ke {meta_path} "
                f"(Normal: {normal_acc*100:.1f}%, Thresh: {normal_th*100:.1f}%, "
                f"Runner: {runner_acc*100:.1f}%, Thresh: {runner_th*100:.1f}%, Max RR: {max_runner_rr:.1f}R)"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save models metadata for {symbol}: {e}")
            return False

    @staticmethod
    def save_oos_scorecard(symbol: str, mode: str, scorecard: Dict[str, Any]) -> bool:
        """Menyimpan atau memperbarui OOS scorecard ke models_metadata.json."""
        try:
            sym = str(symbol or "XAUUSD").upper()
            meta_path = ModelManager.get_metadata_path(sym)
            meta: Dict[str, Any] = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r") as f:
                        meta = json.load(f)
                except Exception:
                    meta = {}

            meta["symbol"] = sym
            mode_clean = str(mode).strip().lower()
            if mode_clean not in meta:
                meta[mode_clean] = {}
            meta[mode_clean]["oos_scorecard"] = scorecard
            if "oos_scorecard" not in meta:
                meta["oos_scorecard"] = {}
            meta["oos_scorecard"][mode_clean] = scorecard

            os.makedirs(os.path.dirname(meta_path), exist_ok=True)
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
            logger.info(f"[RESEARCHER-{sym}] OOS Scorecard ({mode_clean}) tersimpan ke {meta_path}")
            return True
        except Exception as e:
            logger.error(f"Gagal menyimpan OOS Scorecard untuk {symbol}: {e}")
            return False

    @staticmethod
    def save_models(
        symbol: str,
        model_normal: Any = None,
        model_runner: Any = None,
        **metadata_kwargs
    ) -> bool:
        try:
            sym = str(symbol or "XAUUSD").upper()
            path_normal = ModelManager.get_model_path(sym, "normal")
            path_runner = ModelManager.get_model_path(sym, "runner")

            if model_normal is not None:
                joblib.dump(model_normal, path_normal)
            if model_runner is not None:
                joblib.dump(model_runner, path_runner)

            metadata_kwargs["normal_trained"] = model_normal is not None
            metadata_kwargs["runner_trained"] = model_runner is not None
            ModelManager.save_metadata(symbol=sym, **metadata_kwargs)

            logger.info(f"Model checkpoints and metadata saved to '{ModelManager.get_model_dir(sym)}' directory.")
            return True
        except Exception as e:
            logger.error(f"Failed to save models for {symbol}: {e}")
            return False

    @staticmethod
    def load_models(symbol: str) -> Dict[str, Any]:
        """
        Memuat model dan metadata untuk symbol tertentu.
        Mengembalikan dictionary berisi model_normal, model_runner, features, metadata.
        """
        sym = str(symbol or "XAUUSD").upper()
        res = {
            "model_normal": None,
            "model_runner": None,
            "features": [],
            "last_accuracy_normal": 0.0,
            "last_trained_normal": None,
            "optimal_threshold_normal": 0.54,
            "last_accuracy_runner": 0.0,
            "last_trained_runner": None,
            "optimal_threshold_runner": 0.54,
            "max_runner_rr": 5.0,
            "loaded": False
        }
        try:
            path_normal = ModelManager.get_model_path(sym, "normal")
            path_runner = ModelManager.get_model_path(sym, "runner")
            meta_path = ModelManager.get_metadata_path(sym)

            # Fallback ke root models/ jika file belum dipindahkan
            target_normal = path_normal if os.path.exists(path_normal) else "models/model_normal.pkl"
            target_runner = path_runner if os.path.exists(path_runner) else "models/model_runner.pkl"

            loaded_any = False
            if os.path.exists(target_normal) and os.path.getsize(target_normal) > 100:
                res["model_normal"] = joblib.load(target_normal)
                loaded_any = True
                logger.info(f"[RESEARCHER-{sym}] Model Normal loaded from {target_normal}")

            if os.path.exists(target_runner) and os.path.getsize(target_runner) > 100:
                res["model_runner"] = joblib.load(target_runner)
                loaded_any = True
                logger.info(f"[RESEARCHER-{sym}] Model Runner loaded from {target_runner}")

            if loaded_any:
                res["loaded"] = True
                # Extract features dari model yang tersimpan
                m = res["model_normal"] or res["model_runner"]
                if hasattr(m, 'feature_name_'):
                    res["features"] = list(m.feature_name_)
                elif hasattr(m, 'booster_'):
                    res["features"] = m.booster_.feature_name()

                # Baca metadata
                target_meta = meta_path if os.path.exists(meta_path) else "models/models_metadata.json"
                if os.path.exists(target_meta):
                    try:
                        with open(target_meta, "r") as f:
                            meta = json.load(f)
                        res["last_accuracy_normal"] = float(meta.get("normal", {}).get("last_accuracy", 0.0))
                        res["last_trained_normal"] = meta.get("normal", {}).get("last_trained_at")
                        res["optimal_threshold_normal"] = float(meta.get("normal", {}).get("optimal_threshold", 0.54))
                        res["last_accuracy_runner"] = float(meta.get("runner", {}).get("last_accuracy", 0.0))
                        res["last_trained_runner"] = meta.get("runner", {}).get("last_trained_at")
                        res["optimal_threshold_runner"] = float(meta.get("runner", {}).get("optimal_threshold", 0.54))
                        res["max_runner_rr"] = float(meta.get("runner", {}).get("max_runner_rr", 5.0))
                        res["oos_scorecard"] = meta.get("oos_scorecard", {
                            "normal": meta.get("normal", {}).get("oos_scorecard"),
                            "runner": meta.get("runner", {}).get("oos_scorecard")
                        })
                        logger.info(
                            f"[RESEARCHER-{sym}] Metadata loaded: Normal Acc={res['last_accuracy_normal']*100:.1f}% "
                            f"(Thresh: {res['optimal_threshold_normal']*100:.1f}%), Runner Acc={res['last_accuracy_runner']*100:.1f}% "
                            f"(Thresh: {res['optimal_threshold_runner']*100:.1f}%), Max Runner RR={res['max_runner_rr']:.1f}R"
                        )
                    except Exception as em:
                        logger.warning(f"Gagal membaca metadata {target_meta}: {em}")

        except Exception as e:
            logger.error(f"Failed to load models for {sym}: {e}")

        return res
