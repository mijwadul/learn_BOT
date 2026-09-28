import json
import logging
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("SettingsManager")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "risk_mode": "fixed",
    "fixed_lot_size": 0.01,
    "max_risk_dollars": 10.0,
    "max_risk_percent": 1.0,
    "max_lot_cap": 0.10,
    "ai_normal_entry_threshold": 60.0,
    "ai_runner_entry_threshold": 55.0,
    "pairs": {
        "XAUUSD": {
            "threshold": 60.0,
            "ai_normal_entry_threshold": 60.0,
            "ai_runner_entry_threshold": 55.0,
        }
    },
}

class SettingsManager:
    """
    Manages persistent runtime bot settings in bot_settings.json.
    Ensures .env is strictly reserved for read-only credentials/secrets.
    Supports atomic writes, automatic regeneration, and per-pair overrides.
    """

    def __init__(self, settings_path: Optional[Path] = None):
        if settings_path is None:
            env_path = os.getenv("BOT_SETTINGS_FILE")
            if env_path:
                self.filepath = Path(env_path).resolve()
            else:
                self.filepath = Path(__file__).resolve().parent.parent / "bot_settings.json"
        else:
            self.filepath = Path(settings_path).resolve()

        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self.load()

    def _get_env_fallback_defaults(self) -> Dict[str, Any]:
        """Backward compatibility: fallback to existing .env values if generating for the first time."""
        defaults = deepcopy(DEFAULT_SETTINGS)
        if os.getenv("RISK_MODE"):
            defaults["risk_mode"] = os.getenv("RISK_MODE", "fixed").lower()
        if os.getenv("FIXED_LOT_SIZE"):
            try:
                defaults["fixed_lot_size"] = float(os.getenv("FIXED_LOT_SIZE"))
            except ValueError:
                pass
        if os.getenv("MAX_RISK_DOLLARS"):
            try:
                defaults["max_risk_dollars"] = float(os.getenv("MAX_RISK_DOLLARS"))
            except ValueError:
                pass
        if os.getenv("MAX_RISK_PERCENT"):
            try:
                defaults["max_risk_percent"] = float(os.getenv("MAX_RISK_PERCENT"))
            except ValueError:
                pass
        if os.getenv("MAX_LOT_CAP"):
            try:
                defaults["max_lot_cap"] = float(os.getenv("MAX_LOT_CAP"))
            except ValueError:
                pass
        if os.getenv("AI_NORMAL_ENTRY_THRESHOLD"):
            try:
                th = float(os.getenv("AI_NORMAL_ENTRY_THRESHOLD"))
                defaults["ai_normal_entry_threshold"] = th
                if "XAUUSD" in defaults.get("pairs", {}):
                    defaults["pairs"]["XAUUSD"]["ai_normal_entry_threshold"] = th
                    defaults["pairs"]["XAUUSD"]["threshold"] = th
            except ValueError:
                pass
        if os.getenv("AI_RUNNER_ENTRY_THRESHOLD"):
            try:
                defaults["ai_runner_entry_threshold"] = float(os.getenv("AI_RUNNER_ENTRY_THRESHOLD"))
            except ValueError:
                pass
        return defaults

    def load(self) -> Dict[str, Any]:
        """Loads settings from bot_settings.json or regenerates default values if missing or invalid."""
        with self._lock:
            if not self.filepath.exists():
                logger.info(f"[SettingsManager] {self.filepath.name} tidak ditemukan. Membuat file baru dengan default...")
                self._data = self._get_env_fallback_defaults()
                self._save_to_disk()
                return deepcopy(self._data)

            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        # Ensure all default keys exist
                        merged = deepcopy(DEFAULT_SETTINGS)
                        merged.update(loaded)
                        # Ensure pairs key is a dict
                        if "pairs" not in merged or not isinstance(merged["pairs"], dict):
                            merged["pairs"] = deepcopy(DEFAULT_SETTINGS["pairs"])
                        self._data = merged
                    else:
                        logger.warning(f"[SettingsManager] Format {self.filepath.name} tidak valid. Menggunakan default...")
                        self._data = self._get_env_fallback_defaults()
                        self._save_to_disk()
            except Exception as e:
                logger.error(f"[SettingsManager] Gagal membaca {self.filepath}: {e}. Meregenerasi file aman...")
                self._data = self._get_env_fallback_defaults()
                self._save_to_disk()

            return deepcopy(self._data)

    def _save_to_disk(self):
        """Atomic write using temporary file to prevent corruption on crash or power failure."""
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = self.filepath.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            os.replace(tmp_file, self.filepath)
        except Exception as e:
            logger.error(f"[SettingsManager] Gagal menulis atomic file {self.filepath}: {e}")
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass
            raise

    def get_setting(self, key: str, default: Any = None, symbol: Optional[str] = None) -> Any:
        """
        Mengambil nilai konfigurasi.
        Jika `symbol` diberikan, periksa override per-pair terlebih dahulu sebelum fallback ke global setting.
        """
        with self._lock:
            if symbol:
                sym_clean = str(symbol).strip().upper()
                pairs = self._data.get("pairs", {})
                pair_cfg = pairs.get(sym_clean)
                if isinstance(pair_cfg, dict):
                    if key in pair_cfg:
                        return pair_cfg[key]
                    # Alias compatibility: threshold <-> ai_normal_entry_threshold
                    if key == "ai_normal_entry_threshold" and "threshold" in pair_cfg:
                        val = pair_cfg["threshold"]
                        return val * 100.0 if (isinstance(val, (int, float)) and 0.0 < val <= 1.0) else val
                    if key == "threshold" and "ai_normal_entry_threshold" in pair_cfg:
                        return pair_cfg["ai_normal_entry_threshold"]

            if key in self._data:
                return self._data[key]
            return default

    def get_ai_threshold(self, symbol: Optional[str] = None, mode: str = "normal") -> float:
        """Helper praktis untuk mendapatkan AI entry threshold (%) dengan dukungan per-pair override."""
        key = "ai_runner_entry_threshold" if mode == "runner" else "ai_normal_entry_threshold"
        default = 55.0 if mode == "runner" else 60.0
        val = self.get_setting(key, default, symbol=symbol)
        try:
            val_float = float(val)
            # Jika dalam format pecahan 0.0 - 1.0 (misal 0.62), konversi ke persen (62.0)
            if 0.0 < val_float <= 1.0:
                val_float *= 100.0
            return val_float
        except (ValueError, TypeError):
            return default

    def update_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Memperbarui konfigurasi runtime secara aman dan persisten.
        Mendukung pembaruan parameter global maupun override pair.
        """
        with self._lock:
            for k, v in updates.items():
                if k in ("pairs", "pair_overrides") and isinstance(v, dict):
                    if "pairs" not in self._data or not isinstance(self._data["pairs"], dict):
                        self._data["pairs"] = {}
                    for sym, pair_cfg in v.items():
                        sym_clean = str(sym).strip().upper()
                        if isinstance(pair_cfg, dict):
                            clean_cfg = dict(pair_cfg)
                            if "threshold" in clean_cfg:
                                th = clean_cfg["threshold"]
                                clean_cfg["ai_normal_entry_threshold"] = (
                                    float(th) * 100.0 if (isinstance(th, (int, float)) and 0.0 < th <= 1.0) else float(th)
                                )
                                clean_cfg["threshold"] = (
                                    float(th) / 100.0 if (isinstance(th, (int, float)) and th > 1.0) else float(th)
                                )
                            elif "ai_normal_entry_threshold" in clean_cfg:
                                th = clean_cfg["ai_normal_entry_threshold"]
                                clean_cfg["threshold"] = (
                                    float(th) / 100.0 if (isinstance(th, (int, float)) and th > 1.0) else float(th)
                                )
                                clean_cfg["ai_normal_entry_threshold"] = float(th)

                            if sym_clean not in self._data["pairs"]:
                                self._data["pairs"][sym_clean] = {}
                            self._data["pairs"][sym_clean].update(clean_cfg)
                else:
                    self._data[k] = v

            self._save_to_disk()
            return deepcopy(self._data)

    def set_pair_override(self, symbol: str, overrides: Dict[str, Any]) -> Dict[str, Any]:
        """Menyetel atau memperbarui konfigurasi spesifik pair (misal threshold per-pair)."""
        sym_clean = str(symbol).strip().upper()
        return self.update_settings({"pairs": {sym_clean: overrides}})

    def get_all_settings(self) -> Dict[str, Any]:
        """Mengembalikan seluruh konfigurasi runtime."""
        with self._lock:
            return deepcopy(self._data)

# Singleton global instance
settings_manager = SettingsManager()

def get_setting(key: str, default: Any = None, symbol: Optional[str] = None) -> Any:
    return settings_manager.get_setting(key, default, symbol=symbol)

def update_settings(updates: Dict[str, Any]) -> Dict[str, Any]:
    return settings_manager.update_settings(updates)

def get_ai_threshold(symbol: Optional[str] = None, mode: str = "normal") -> float:
    return settings_manager.get_ai_threshold(symbol=symbol, mode=mode)
