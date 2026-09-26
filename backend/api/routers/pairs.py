import os
import json
import logging
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from config import Config
from utils.mt5_utils import resolve_broker_symbol
from database import sync_engine, get_market_table_name, get_db_size
from ..dependencies import bot

router = APIRouter(tags=["Multi-Pair Management"])

class PairAddRequest(BaseModel):
    symbol: str

class PairToggleRequest(BaseModel):
    symbol: str
    active: bool

REGISTRY_FILE = Path("registered_pairs.json")

def load_registered_pairs() -> List[str]:
    """Muat daftar pair yang didaftarkan secara eksplisit oleh pengguna."""
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    clean = [str(s).strip().upper() for s in data if str(s).strip()]
                    if "XAUUSD" not in clean:
                        clean.insert(0, "XAUUSD")
                    return sorted(list(set(clean)))
        except Exception as e:
            logging.error(f"[PAIRS] Gagal membaca registered_pairs.json: {e}")
    # Default hanya XAUUSD
    save_registered_pairs(["XAUUSD"])
    return ["XAUUSD"]

def save_registered_pairs(pairs: List[str]):
    clean = sorted(list(set([str(p).strip().upper() for p in pairs if str(p).strip()])))
    if "XAUUSD" not in clean:
        clean.insert(0, "XAUUSD")
    try:
        with open(REGISTRY_FILE, "w") as f:
            json.dump(clean, f, indent=2)
    except Exception as e:
        logging.error(f"[PAIRS] Gagal menyimpan registered_pairs.json: {e}")

def discover_available_pairs() -> List[str]:
    """
    Hanya mengembalikan pair yang terdaftar resmi di registered_pairs.json
    dan subfolder models/{PAIR}/ yang valid (default awal hanya XAUUSD).
    Tidak memindai tabel sembarang di database.
    """
    pairs = set(load_registered_pairs())
    pairs.add("XAUUSD")
    
    # Pindai folder models/ untuk subfolder pair yang dibuat
    models_dir = Path("models")
    if models_dir.exists():
        for item in models_dir.iterdir():
            if item.is_dir() and not item.name.startswith(".") and not item.name.startswith("_"):
                sym = item.name.upper()
                if len(sym) >= 3 and sym.isalnum():
                    pairs.add(sym)

    return sorted(list(pairs))

@router.get("/api/pairs")
async def list_pairs():
    """
    Mengembalikan daftar seluruh pair yang terdaftar di sistem beserta status
    otak (normal & runner model), resolusi broker MT5, jumlah data candle, dan status live active.
    """
    discovered = discover_available_pairs()
    active_set = set(getattr(bot, "active_pairs", ["XAUUSD"]))

    result = []
    for sym in discovered:
        clean_sym = sym.upper()
        norm_pkl = Path("models") / clean_sym / "model_normal.pkl"
        run_pkl = Path("models") / clean_sym / "model_runner.pkl"
        meta_file = Path("models") / clean_sym / "models_metadata.json"

        # Fallback root untuk XAUUSD jika belum dipindah
        if clean_sym == "XAUUSD" and not norm_pkl.exists():
            norm_pkl = Path("models/model_normal.pkl")
            run_pkl = Path("models/model_runner.pkl")
            meta_file = Path("models/models_metadata.json")

        meta = {}
        if meta_file.exists():
            try:
                with open(meta_file, "r") as f:
                    meta = json.load(f)
            except Exception:
                pass

        broker_sym = resolve_broker_symbol(clean_sym)
        table_name = get_market_table_name(clean_sym)
        row_count = get_db_size(clean_sym)

        result.append({
            "symbol": clean_sym,
            "broker_symbol": broker_sym,
            "table_name": table_name,
            "row_count": row_count,
            "has_normal_model": norm_pkl.exists(),
            "has_runner_model": run_pkl.exists(),
            "last_accuracy_normal": float(meta.get("normal", {}).get("last_accuracy", 0.0)),
            "last_accuracy_runner": float(meta.get("runner", {}).get("last_accuracy", 0.0)),
            "is_active": clean_sym in active_set,
        })

    return {
        "status": "success",
        "active_pairs": list(active_set),
        "pairs": result
    }

@router.post("/api/pairs/add")
async def add_pair(req: PairAddRequest):
    """
    Mendaftarkan pair baru ke dalam sistem:
    - Menyiapkan subfolder models/{SYMBOL}/
    - Memverifikasi nama instrumen di broker MT5
    """
    clean_sym = req.symbol.strip().upper()
    if not clean_sym:
        return {"status": "error", "message": "Nama symbol tidak boleh kosong."}

    # Buat subfolder otak
    folder = Path("models") / clean_sym
    folder.mkdir(parents=True, exist_ok=True)

    broker_sym = resolve_broker_symbol(clean_sym)

    # Inisialisasi metadata kosong jika belum ada
    meta_path = folder / "models_metadata.json"
    if not meta_path.exists():
        with open(meta_path, "w") as f:
            json.dump({
                "symbol": clean_sym,
                "normal": {"last_accuracy": 0.0, "last_trained_at": None, "trained": False},
                "runner": {"last_accuracy": 0.0, "last_trained_at": None, "trained": False}
            }, f, indent=2)

    # Simpan ke daftar registered_pairs.json
    current_reg = load_registered_pairs()
    if clean_sym not in current_reg:
        current_reg.append(clean_sym)
        save_registered_pairs(current_reg)

    return {
        "status": "success",
        "message": f"Pair {clean_sym} berhasil didaftarkan. Terdeteksi di broker MT5 sebagai [{broker_sym}].",
        "symbol": clean_sym,
        "broker_symbol": broker_sym,
        "table_name": get_market_table_name(clean_sym)
    }

@router.post("/api/pairs/remove")
async def remove_pair(req: PairAddRequest):
    """
    Menghapus pair dari daftar pemantauan (XAUUSD dilindungi tidak bisa dihapus).
    """
    clean_sym = req.symbol.strip().upper()
    if clean_sym == "XAUUSD":
        return {"status": "error", "message": "XAUUSD adalah pair default dan tidak dapat dihapus."}
    
    current_reg = load_registered_pairs()
    if clean_sym in current_reg:
        current_reg.remove(clean_sym)
        save_registered_pairs(current_reg)
        return {"status": "success", "message": f"Pair {clean_sym} berhasil dihapus dari daftar."}
    return {"status": "error", "message": f"Pair {clean_sym} tidak ditemukan dalam daftar."}

@router.post("/api/pairs/toggle")
async def toggle_pair(req: PairToggleRequest):
    """
    Mengaktifkan / menonaktifkan eksekusi live trading untuk pair tertentu.
    Bisa mengaktifkan 1 pair, keduanya, atau lebih.
    """
    clean_sym = req.symbol.strip().upper()
    if not hasattr(bot, "active_pairs"):
        bot.active_pairs = ["XAUUSD"]

    if req.active:
        if clean_sym not in bot.active_pairs:
            bot.active_pairs.append(clean_sym)
    else:
        if clean_sym in bot.active_pairs:
            bot.active_pairs.remove(clean_sym)
        # Jangan biarkan kosong, default ke XAUUSD jika semua dimatikan
        if not bot.active_pairs:
            bot.active_pairs = ["XAUUSD"]

    return {
        "status": "success",
        "symbol": clean_sym,
        "active": req.active,
        "active_pairs": bot.active_pairs,
        "message": f"Pair {clean_sym} {'diaktifkan' if req.active else 'dinonaktifkan'} untuk live trading."
    }
