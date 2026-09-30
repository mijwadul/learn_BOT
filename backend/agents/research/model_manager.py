import os
import json
import logging
import math
import joblib
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

def sanitize_json_floats(obj: Any) -> Any:
    """Konversi nilai float inf, -inf, dan NaN menjadi angka float finite yang valid untuk JSON."""
    if isinstance(obj, float):
        if math.isnan(obj):
            return 0.0
        if math.isinf(obj):
            return 999.0 if obj > 0 else -999.0
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_json_floats(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_json_floats(v) for v in obj]
    return obj

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
    def get_candidate_model_path(symbol: str, mode: str) -> str:
        d = ModelManager.get_model_dir(symbol)
        return os.path.join(d, f"model_{mode}_candidate.pkl")

    @staticmethod
    def get_pending_model_path(symbol: str, mode: str) -> str:
        d = ModelManager.get_model_dir(symbol)
        return os.path.join(d, f"model_{mode}_pending.pkl")

    @staticmethod
    def get_pending_info_path(symbol: str, mode: str) -> str:
        d = ModelManager.get_model_dir(symbol)
        return os.path.join(d, f"pending_{mode}_info.json")

    @staticmethod
    def save_pending_model(symbol: str, mode: str, model: Any, info: Dict[str, Any]) -> bool:
        """Menyimpan model hasil training baru sebagai checkpoint pending tanpa menimpa .pkl lama."""
        try:
            sym = str(symbol or "XAUUSD").upper()
            mode_clean = str(mode).strip().lower()
            p_model = ModelManager.get_pending_model_path(sym, mode_clean)
            p_info = ModelManager.get_pending_info_path(sym, mode_clean)
            joblib.dump(model, p_model)
            cleaned_info = sanitize_json_floats(info)
            with open(p_info, "w") as f:
                json.dump(cleaned_info, f, indent=2)
            logger.info(f"💾 [RESEARCHER-{sym}] Model pending ({mode_clean}) tersimpan di {p_model}. Menunggu konfirmasi user.")
            return True
        except Exception as e:
            logger.error(f"Gagal menyimpan model pending ({mode}) untuk {symbol}: {e}")
            return False

    @staticmethod
    def get_pending_info(symbol: str, mode: str) -> Optional[Dict[str, Any]]:
        """Membaca metadata model pending yang belum dikonfirmasi jika ada."""
        try:
            sym = str(symbol or "XAUUSD").upper()
            mode_clean = str(mode).strip().lower()
            p_info = ModelManager.get_pending_info_path(sym, mode_clean)
            p_model = ModelManager.get_pending_model_path(sym, mode_clean)
            if os.path.exists(p_info) and os.path.exists(p_model):
                with open(p_info, "r") as f:
                    raw_data = json.load(f)
                    return sanitize_json_floats(raw_data)
        except Exception as e:
            logger.warning(f"Gagal membaca pending info ({mode}) untuk {symbol}: {e}")
        return None

    @staticmethod
    def load_pending_model(symbol: str, mode: str) -> Optional[Any]:
        """Memuat objek model pending dari disk."""
        try:
            sym = str(symbol or "XAUUSD").upper()
            mode_clean = str(mode).strip().lower()
            p_model = ModelManager.get_pending_model_path(sym, mode_clean)
            if os.path.exists(p_model) and os.path.getsize(p_model) > 100:
                return joblib.load(p_model)
        except Exception as e:
            logger.warning(f"Gagal memuat pending model ({mode}) untuk {symbol}: {e}")
        return None

    @staticmethod
    def discard_pending_model(symbol: str, mode: str) -> bool:
        """Menghapus file model pending dan infonya dari disk."""
        try:
            sym = str(symbol or "XAUUSD").upper()
            mode_clean = str(mode).strip().lower()
            p_model = ModelManager.get_pending_model_path(sym, mode_clean)
            p_info = ModelManager.get_pending_info_path(sym, mode_clean)
            if os.path.exists(p_model):
                os.remove(p_model)
            if os.path.exists(p_info):
                os.remove(p_info)
            logger.info(f"🗑️ [RESEARCHER-{sym}] File pending model & info ({mode_clean}) telah dibersihkan.")
            return True
        except Exception as e:
            logger.warning(f"Gagal menghapus file pending ({mode}) untuk {symbol}: {e}")
            return False

    @staticmethod
    def reset_all_models_and_metrics(symbol: str) -> list:
        """
        Menghapus seluruh file model (.pkl), candidate (.pkl), pending (.pkl),
        dan seluruh metadata/metric (.json) di folder models/{symbol}/.
        """
        sym = str(symbol or "XAUUSD").upper()
        deleted = []
        d = ModelManager.get_model_dir(sym)
        if os.path.exists(d):
            for fname in os.listdir(d):
                fpath = os.path.join(d, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                        deleted.append(fname)
                        logger.info(f"🗑️ [RESET - {sym}] Menghapus file: {fpath}")
                    except Exception as e:
                        logger.warning(f"Gagal menghapus file {fpath}: {e}")

        # Hapus legacy XAUUSD jika ada di root models/
        if sym == "XAUUSD":
            for legacy in ["model_normal.pkl", "model_runner.pkl", "models_metadata.json", "candidate_normal_metadata.json", "candidate_runner_metadata.json"]:
                lpath = os.path.join("models", legacy)
                if os.path.exists(lpath) and os.path.isfile(lpath):
                    try:
                        os.remove(lpath)
                        deleted.append(legacy)
                        logger.info(f"🗑️ [RESET - {sym}] Menghapus legacy file: {lpath}")
                    except Exception as e:
                        logger.warning(f"Gagal menghapus legacy file {lpath}: {e}")
        return deleted

    @staticmethod
    def get_metadata_path(symbol: str) -> str:
        d = ModelManager.get_model_dir(symbol)
        return os.path.join(d, "models_metadata.json")

    @staticmethod
    def _clean_scorecard(card: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Menghapus array trade individual yang berat sebelum serialisasi metadata JSON."""
        if not card or not isinstance(card, dict):
            return card
        cleaned = card.copy()
        cleaned.pop("losing_records", None)
        cleaned.pop("harvested_hard_negatives", None)
        return cleaned

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

            normal_card = ModelManager._clean_scorecard(normal_card)
            runner_card = ModelManager._clean_scorecard(runner_card)

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
        """Menyimpan atau memperbarui OOS scorecard ke models_metadata.json (sanitized)."""
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

            clean_card = ModelManager._clean_scorecard(scorecard)
            meta["symbol"] = sym
            mode_clean = str(mode).strip().lower()
            if mode_clean not in meta:
                meta[mode_clean] = {}
            meta[mode_clean]["oos_scorecard"] = clean_card
            if "oos_scorecard" not in meta:
                meta["oos_scorecard"] = {}
            meta["oos_scorecard"][mode_clean] = clean_card

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
    def save_candidate_model(
        symbol: str,
        mode: str,
        model: Any,
        scorecard: Optional[Dict[str, Any]] = None,
        features: Optional[list] = None
    ) -> bool:
        """
        Menyimpan checkpoint model yang belum lolos OOS Fit & Proper Test sebagai model kandidat.
        Model ini sangat bernilai untuk dijadikan bobot dasar (init_model) pada incremental training berikutnya.
        """
        try:
            sym = str(symbol or "XAUUSD").upper()
            mode_clean = str(mode).strip().lower()
            path_candidate = ModelManager.get_candidate_model_path(sym, mode_clean)
            joblib.dump(model, path_candidate)

            # Catat metadata kandidat
            cand_meta_path = os.path.join(ModelManager.get_model_dir(sym), f"candidate_{mode_clean}_metadata.json")
            cand_meta = {
                "symbol": sym,
                "mode": mode_clean,
                "saved_at": scorecard.get("evaluated_at") if scorecard else None,
                "metrics": scorecard.get("metrics", {}) if scorecard else {},
                "reasons": scorecard.get("reasons", []) if scorecard else [],
                "threshold_used": scorecard.get("threshold_used", 0.0) if scorecard else 0.0,
                "features": features or []
            }
            with open(cand_meta_path, "w") as f:
                json.dump(cand_meta, f, indent=2)

            logger.info(f"💾 [RESEARCHER-{sym}] Checkpoint model kandidat ({mode_clean}) tersimpan di {path_candidate} untuk incremental training.")
            return True
        except Exception as e:
            logger.error(f"Gagal menyimpan model kandidat ({mode}) untuk {symbol}: {e}")
            return False

    @staticmethod
    def load_candidate_model(symbol: str, mode: str) -> Optional[Any]:
        """
        Memuat checkpoint model kandidat yang tersimpan jika ada.
        """
        try:
            sym = str(symbol or "XAUUSD").upper()
            mode_clean = str(mode).strip().lower()
            path_candidate = ModelManager.get_candidate_model_path(sym, mode_clean)
            if os.path.exists(path_candidate) and os.path.getsize(path_candidate) > 100:
                model = joblib.load(path_candidate)
                logger.info(f"📂 [RESEARCHER-{sym}] Berhasil memuat model kandidat ({mode_clean}) dari {path_candidate}")
                return model
        except Exception as e:
            logger.warning(f"Gagal memuat model kandidat ({mode}) untuk {symbol}: {e}")
        return None

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
