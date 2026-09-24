import logging
import threading
import asyncio
from datetime import datetime
from fastapi import APIRouter
import pandas as pd
import MetaTrader5 as mt5

from config import Config
from ..dependencies import bot, sync_state, sync_lock

router = APIRouter(tags=["Data Sync & Database Health"])

@router.post("/api/data/sync")
async def sync_data_endpoint():
    """
    Sinkronisasi Cepat MT5 (Inkremental):
    Menarik selisih candle baru sejak record terakhir dan me-append ke market_data_merged.
    """
    with sync_lock:
        if sync_state["is_syncing"]:
            return {"status": "busy", "message": "Proses sinkronisasi data sedang berjalan...", "sync_status": sync_state}
    
    if not bot.mt5_connected:
        bot.connect_mt5()
        if not bot.mt5_connected:
            return {"status": "error", "message": "Gagal terhubung ke MT5. Pastikan MetaTrader 5 aktif dan login broker valid."}

    def run_sync():
        with sync_lock:
            sync_state["is_syncing"] = True
            sync_state["sync_type"] = "incremental"
            sync_state["progress"] = 0
            sync_state["message"] = "Mengecek candle terbaru dari MT5..."
            sync_state["error"] = None

        try:
            try:
                bot.data_miner.get_live_calendar()
            except Exception:
                pass
                
            inserted, msg = bot.data_miner.sync_latest_data()
            with sync_lock:
                sync_state["inserted_rows"] = inserted
                sync_state["last_synced_at"] = datetime.now().isoformat()
                sync_state["message"] = msg
                sync_state["progress"] = 100
        except Exception as e:
            logging.error(f"Error during incremental sync: {e}")
            with sync_lock:
                sync_state["error"] = str(e)
                sync_state["message"] = f"Gagal sinkronisasi: {e}"
        finally:
            with sync_lock:
                sync_state["is_syncing"] = False

    threading.Thread(target=run_sync, daemon=True).start()
    return {
        "status": "success", 
        "message": "Sinkronisasi candle terbaru dari MT5 dimulai di background.",
        "sync_status": sync_state
    }

@router.post("/api/data/backfill")
async def force_backfill_endpoint():
    """
    Force Backfill (Rebuild):
    Men-drop tabel dan men-download ulang 5.000.000 candle secara penuh.
    """
    with sync_lock:
        if sync_state["is_syncing"]:
            return {"status": "busy", "message": "Proses sinkronisasi data sedang berjalan...", "sync_status": sync_state}
    
    if not bot.mt5_connected:
        bot.connect_mt5()
        if not bot.mt5_connected:
            return {"status": "error", "message": "Gagal terhubung ke MT5."}

    if bot.supervisor.state != 'ingestion':
        bot.supervisor.start_ingestion()

    def run_backfill():
        with sync_lock:
            sync_state["is_syncing"] = True
            sync_state["sync_type"] = "backfill"
            sync_state["progress"] = 0
            sync_state["message"] = "Memulai Force Backfill (Rebuild 5,000,000 candles)..."
            sync_state["error"] = None
        
        def progress_cb(current_b, total_b, cur, tot):
            with sync_lock:
                sync_state["progress"] = int((current_b / max(1, total_b)) * 100)
                sync_state["message"] = f"Menyimpan batch {current_b}/{total_b} ({sync_state['progress']}%) ke database..."

        try:
            inserted = bot.data_miner.backfill_data(
                total_candles=5000000,
                progress_callback=progress_cb,
                force_rebuild=True
            )
            with sync_lock:
                sync_state["inserted_rows"] = inserted
                sync_state["last_synced_at"] = datetime.now().isoformat()
                sync_state["message"] = f"Sukses Force Backfill: {inserted:,} candle tersimpan ke database."
                sync_state["progress"] = 100
        except Exception as e:
            logging.error(f"Error during backfill: {e}")
            with sync_lock:
                sync_state["error"] = str(e)
                sync_state["message"] = f"Gagal backfill: {e}"
        finally:
            with sync_lock:
                sync_state["is_syncing"] = False

    threading.Thread(target=run_backfill, daemon=True).start()
    return {
        "status": "success", 
        "message": "Force Backfill MT5 dimulai di background. Cek terminal logs.",
        "sync_status": sync_state
    }

@router.get("/api/data/sync/status")
async def get_sync_status():
    with sync_lock:
        return dict(sync_state)

@router.get("/api/database/health")
async def get_database_health():
    """
    P0-1: Async database size and MT5 status query without blocking the main event loop.
    """
    try:
        from database import get_db_size, get_db_date_range
        row_count = await asyncio.to_thread(get_db_size)
        min_date, max_date = await asyncio.to_thread(get_db_date_range)

        mt5_latest_time = None
        if bot.mt5_connected:
            try:
                rates_last = await asyncio.to_thread(mt5.copy_rates_from_pos, Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 1)
                if rates_last is not None and len(rates_last) > 0:
                    mt5_latest_time = pd.to_datetime(rates_last[0]['time'], unit='s').isoformat()
            except Exception:
                pass

        return {
            "status": "success",
            "row_count": row_count,
            "min_date": min_date.isoformat() if min_date else None,
            "max_date": max_date.isoformat() if max_date else None,
            "mt5_connected": bot.mt5_connected,
            "mt5_latest_time": mt5_latest_time,
            "active_symbol": Config.SYMBOL,
            "is_syncing": sync_state["is_syncing"],
            "sync_progress": sync_state["progress"],
            "last_synced_at": sync_state["last_synced_at"]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
