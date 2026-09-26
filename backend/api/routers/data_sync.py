import logging
import threading
import asyncio
from typing import Optional
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
import pandas as pd
import MetaTrader5 as mt5

from sqlalchemy import text
from config import Config
from utils.mt5_utils import resolve_broker_symbol
from database import sync_engine, get_db_size, get_db_date_range, get_market_table_name
from ..dependencies import bot, sync_state, sync_lock

router = APIRouter(tags=["Data Sync & Database Health"])

class SyncRequest(BaseModel):
    symbol: Optional[str] = "XAUUSD"
    force_rebuild: Optional[bool] = False
    total_candles: Optional[int] = 5000000

@router.post("/api/data/sync")
async def sync_data_endpoint(req: Optional[SyncRequest] = None):
    """
    Sinkronisasi Cepat MT5 (Inkremental):
    Menarik selisih candle baru sejak record terakhir dan me-append ke tabel pair bersangkutan.
    """
    target_symbol = (req.symbol if req and req.symbol else Config.SYMBOL) or "XAUUSD"

    with sync_lock:
        if sync_state["is_syncing"]:
            return {"status": "busy", "message": "Proses sinkronisasi data sedang berjalan...", "sync_status": sync_state}
    
    if not bot.mt5_connected:
        bot.connect_mt5()
        if not bot.mt5_connected:
            return {"status": "error", "message": "Gagal terhubung ke MT5. Pastikan MetaTrader 5 aktif dan login broker valid."}

    # Set target symbol pada miner
    bot.data_miner.set_symbol(target_symbol)

    def run_sync():
        with sync_lock:
            sync_state["is_syncing"] = True
            sync_state["sync_type"] = "incremental"
            sync_state["symbol"] = bot.data_miner.canonical_symbol
            sync_state["progress"] = 0
            sync_state["message"] = f"Mengecek candle terbaru {bot.data_miner.canonical_symbol} dari MT5..."
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
            logging.error(f"Error during incremental sync ({target_symbol}): {e}")
            with sync_lock:
                sync_state["error"] = str(e)
                sync_state["message"] = f"Gagal sinkronisasi {target_symbol}: {e}"
        finally:
            with sync_lock:
                sync_state["is_syncing"] = False

    threading.Thread(target=run_sync, daemon=True).start()
    return {
        "status": "success", 
        "message": f"Sinkronisasi candle {bot.data_miner.canonical_symbol} ({bot.data_miner.broker_symbol}) dimulai di background.",
        "symbol": bot.data_miner.canonical_symbol,
        "table": bot.data_miner.table_name,
        "sync_status": sync_state
    }

@router.post("/api/data/backfill")
async def force_backfill_endpoint(req: Optional[SyncRequest] = None):
    """
    Force Backfill (Rebuild):
    Men-drop tabel khusus pair dan men-download ulang candle secara penuh.
    """
    target_symbol = (req.symbol if req and req.symbol else Config.SYMBOL) or "XAUUSD"
    total_candles = req.total_candles if req and req.total_candles else 5000000

    with sync_lock:
        if sync_state["is_syncing"]:
            return {"status": "busy", "message": "Proses sinkronisasi data sedang berjalan...", "sync_status": sync_state}
    
    if not bot.mt5_connected:
        bot.connect_mt5()
        if not bot.mt5_connected:
            return {"status": "error", "message": "Gagal terhubung ke MT5."}

    if bot.supervisor.state != 'ingestion':
        bot.supervisor.start_ingestion()

    bot.data_miner.set_symbol(target_symbol)

    def run_backfill():
        with sync_lock:
            sync_state["is_syncing"] = True
            sync_state["sync_type"] = "backfill"
            sync_state["symbol"] = bot.data_miner.canonical_symbol
            sync_state["progress"] = 0
            sync_state["message"] = f"Memulai Force Backfill ({total_candles:,} candles) untuk {bot.data_miner.canonical_symbol}..."
            sync_state["error"] = None
        
        def progress_cb(current_b, total_b, cur, tot):
            with sync_lock:
                sync_state["progress"] = int((current_b / max(1, total_b)) * 100)
                sync_state["message"] = f"Menyimpan batch {current_b}/{total_b} ({sync_state['progress']}%) ke tabel {bot.data_miner.table_name}..."

        try:
            inserted = bot.data_miner.backfill_data(
                total_candles=total_candles,
                progress_callback=progress_cb,
                force_rebuild=True
            )
            with sync_lock:
                sync_state["inserted_rows"] = inserted
                sync_state["last_synced_at"] = datetime.now().isoformat()
                sync_state["message"] = f"Sukses Force Backfill: {inserted:,} candle tersimpan ke tabel {bot.data_miner.table_name}."
                sync_state["progress"] = 100
        except Exception as e:
            logging.error(f"Error during backfill ({target_symbol}): {e}")
            with sync_lock:
                sync_state["error"] = str(e)
                sync_state["message"] = f"Gagal backfill {target_symbol}: {e}"
        finally:
            with sync_lock:
                sync_state["is_syncing"] = False

    threading.Thread(target=run_backfill, daemon=True).start()
    return {
        "status": "success", 
        "message": f"Force Backfill {bot.data_miner.canonical_symbol} ({bot.data_miner.broker_symbol}) dimulai di background.",
        "symbol": bot.data_miner.canonical_symbol,
        "table": bot.data_miner.table_name,
        "sync_status": sync_state
    }

@router.get("/api/data/sync/status")
async def get_sync_status():
    with sync_lock:
        return dict(sync_state)

@router.get("/api/database/health")
async def get_database_health(symbol: Optional[str] = None):
    """
    P0-1: Async database size and MT5 status query without blocking the main event loop.
    Mendukung filter spesifik per pair via query param ?symbol=EURUSD.
    """
    try:
        sym = (symbol or Config.SYMBOL or "XAUUSD").upper()
        table_name = get_market_table_name(sym)
        broker_sym = resolve_broker_symbol(sym)

        # Cek apakah tabel market_data_xauusd sudah direname atau masih market_data_merged
        if sym == "XAUUSD":
            try:
                with sync_engine.connect() as conn:
                    has_new = conn.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name = 'market_data_xauusd'")).scalar()
                    if not has_new:
                        has_old = conn.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name = 'market_data_merged'")).scalar()
                        if has_old:
                            table_name = "market_data_merged"
            except Exception:
                pass

        row_count = await asyncio.to_thread(get_db_size, sym)
        min_date, max_date = await asyncio.to_thread(get_db_date_range, sym)

        mt5_latest_time = None
        if bot.mt5_connected:
            try:
                rates_last = await asyncio.to_thread(mt5.copy_rates_from_pos, broker_sym, mt5.TIMEFRAME_M1, 0, 1)
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
            "active_symbol": sym,
            "broker_symbol": broker_sym,
            "table_name": table_name,
            "is_syncing": sync_state.get("is_syncing", False),
            "sync_progress": sync_state.get("progress", 0),
            "last_synced_at": sync_state.get("last_synced_at")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

