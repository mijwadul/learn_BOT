from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from contextlib import asynccontextmanager
import os
import asyncio
import random
from datetime import datetime
import json
import logging
import threading
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# Import agents
from agents.supervisor import SupervisorAgent
from agents.data_miner import DataMinerAgent
from agents.researcher import ResearcherAgent
from agents.gatekeeper import GatekeeperAgent
from agents.executor import ExecutorAgent
from config import Config
from utils.mt5_utils import init_mt5

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

manager_market = ConnectionManager()
manager_logs = ConnectionManager()

main_loop = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()
    yield

app = FastAPI(
    title="AvantGarde Bot API", 
    description="Backend API for AvantGarde Trading Bot",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom WebSocket Log Handler
class WebSocketLogHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            if main_loop and not main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(
                    manager_logs.broadcast(json.dumps({"type": "log", "message": log_entry})),
                    main_loop
                )
        except Exception:
            pass

ws_handler = WebSocketLogHandler()
ws_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(ws_handler)

# Global State
class BotState:
    def __init__(self):
        self.is_live = False
        self.active_since = None
        self.mt5_connected = False
        
        # Initialize Agents
        self.supervisor = SupervisorAgent()
        self.data_miner = DataMinerAgent(symbol=Config.SYMBOL)
        self.researcher = ResearcherAgent()
        self.gatekeeper = GatekeeperAgent(self.researcher)
        self.executor = ExecutorAgent(
            self.supervisor,
            data_miner_agent=self.data_miner,
            researcher_agent=self.researcher
        )
        self.executor_task = None
        
        # Attempt MT5 Connection
        self.connect_mt5()
        
        # Initialize Models if exists
        if self.researcher.load_models():
            is_norm_ok = self.researcher.last_accuracy_normal >= 0.50 if self.researcher.last_accuracy_normal > 0 else True
            is_run_ok = self.researcher.last_accuracy_runner >= 0.50 if self.researcher.last_accuracy_runner > 0 else True
            self.supervisor.set_model_validity(is_norm_ok, is_run_ok)
            
            # Jika model ada tapi akurasi belum pernah terekam (0.0%), jalankan background OOS evaluation
            if (self.researcher.model_normal is not None and self.researcher.last_accuracy_normal == 0.0) or \
               (self.researcher.model_runner is not None and self.researcher.last_accuracy_runner == 0.0):
                threading.Thread(target=self._auto_validate_loaded_models, daemon=True).start()

    def _auto_validate_loaded_models(self):
        """Memvalidasi model yang ada di disk terhadap OOS jika metadata akurasi kosong (0.0) saat restart."""
        try:
            logging.info("[STARTUP VALIDATION] Model checkpoint ditemukan tanpa metadata akurasi. Menjalankan OOS evaluation...")
            if self.researcher.model_normal is not None and self.researcher.last_accuracy_normal == 0.0:
                total_test_chunks, test_gen = self.data_miner.load_test_chunks(chunk_size=5000)
                if total_test_chunks > 0 and test_gen:
                    acc_n = self.gatekeeper.validate_model('normal', test_gen, total_test_chunks)
                    self.researcher.last_accuracy_normal = float(acc_n)
                    self.researcher.last_trained_normal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if self.researcher.model_runner is not None and self.researcher.last_accuracy_runner == 0.0:
                total_test_chunks, test_gen = self.data_miner.load_test_chunks(chunk_size=5000)
                if total_test_chunks > 0 and test_gen:
                    acc_r = self.gatekeeper.validate_model('runner', test_gen, total_test_chunks)
                    self.researcher.last_accuracy_runner = float(acc_r)
                    self.researcher.last_trained_runner = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            self.researcher.save_metadata()
            self.supervisor.set_model_validity(
                self.researcher.last_accuracy_normal >= 0.50,
                self.researcher.last_accuracy_runner >= 0.50
            )
            logging.info(f"✅ [STARTUP VALIDATION] Selesai. Akurasi tersimpan: Normal={self.researcher.last_accuracy_normal*100:.1f}%, Runner={self.researcher.last_accuracy_runner*100:.1f}%")
        except Exception as e:
            logging.error(f"[STARTUP VALIDATION] Gagal: {e}")

    def connect_mt5(self):
        try:
            if init_mt5(Config.MT5_SERVER, Config.MT5_LOGIN, Config.MT5_PASSWORD, Config.MT5_PATH):
                logging.info("Successfully connected to MT5.")
                self.mt5_connected = True

                # --- SMART SYMBOL AUTO-DETECTION ---
                from utils.mt5_utils import detect_gold_symbol
                resolved_symbol = detect_gold_symbol(Config.SYMBOL)
                Config.SYMBOL = resolved_symbol
                if hasattr(self, 'data_miner') and self.data_miner is not None:
                    self.data_miner.symbol = resolved_symbol
                logging.info(f"🎯 [SMART SYMBOL] Instrumen Gold aktif terdeteksi: {Config.SYMBOL}")

                self.executor.data_miner = self.data_miner
                self.executor.researcher = self.researcher
            else:
                logging.warning("Failed to connect to MT5. Running in mock/offline mode.")
                self.mt5_connected = False
                if Config.SYMBOL == "AUTO":
                    Config.SYMBOL = "XAUUSDm"
                    if hasattr(self, 'data_miner') and self.data_miner is not None:
                        self.data_miner.symbol = Config.SYMBOL
        except Exception as e:
            logging.error(f"MT5 initialization error: {e}")
            self.mt5_connected = False
            if Config.SYMBOL == "AUTO":
                Config.SYMBOL = "XAUUSDm"
                if hasattr(self, 'data_miner') and self.data_miner is not None:
                    self.data_miner.symbol = Config.SYMBOL

bot = BotState()

@app.get("/api/state")
async def get_state():
    # Mengambil metrik aktual dari MT5 dan Database
    win_rate, total_trades, avg_profit, max_drawdown = 0.0, 0, 0.0, 0.0
    mode_performance = {}
    try:
        from database import get_recent_trade_logs, get_trade_performance_summary
        mode_performance = get_trade_performance_summary()
        logs_df = get_recent_trade_logs(100)
        if not logs_df.empty:
            total_trades = len(logs_df)
            wins = len(logs_df[logs_df['profit'] > 0])
            win_rate = round((wins / total_trades) * 100, 1) if total_trades > 0 else 0.0
            avg_profit = round(logs_df['profit'].mean(), 2)
    except Exception:
        pass
        
    open_positions = []
    portfolio_value = 10450.00 # Default/Mock if MT5 is disconnected
    equity = 10450.00
    if bot.mt5_connected:
        try:
            acc = mt5.account_info()
            if acc:
                portfolio_value = acc.balance
                equity = acc.equity
                
            positions = mt5.positions_get(symbol=Config.SYMBOL)
            if positions:
                for p in positions:
                    open_positions.append({
                        "symbol": Config.SYMBOL,
                        "ticket": p.ticket,
                        "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                        "volume": p.volume,
                        "open_price": p.price_open,
                        "current_price": p.price_current,
                        "profit": p.profit
                    })
        except Exception:
            pass

    # Sinkronisasi metadata akurasi jika memori masih 0.0 tapi ada file metadata persisten
    if (bot.researcher.last_accuracy_normal == 0.0 or bot.researcher.last_accuracy_runner == 0.0) and os.path.exists("models/models_metadata.json"):
        try:
            import json as _json
            with open("models/models_metadata.json", "r") as _mf:
                _meta = _json.load(_mf)
            if bot.researcher.last_accuracy_normal == 0.0:
                bot.researcher.last_accuracy_normal = float(_meta.get("normal", {}).get("last_accuracy", 0.0))
            if bot.researcher.last_accuracy_runner == 0.0:
                bot.researcher.last_accuracy_runner = float(_meta.get("runner", {}).get("last_accuracy", 0.0))
        except Exception:
            pass

    # Mengambil event kalender ekonomi High Impact terdekat (Countdown Macro Bridge)
    next_high_impact_news = None
    try:
        from database import get_next_high_impact_event
        if bot.data_miner is not None and bot.mt5_connected:
            bot.data_miner.get_live_calendar()
        next_high_impact_news = get_next_high_impact_event()
    except Exception as e:
        logging.debug(f"Gagal mengambil next high impact news: {e}")

    return {
        "is_live": bot.is_live,
        "active_since": bot.active_since,
        "mt5_connected": bot.mt5_connected,
        "active_symbol": Config.SYMBOL,
        "supervisor_state": bot.supervisor.state,
        "performance": {
            "win_rate": win_rate,
            "total_trades": total_trades,
            "avg_profit": avg_profit,
            "max_drawdown": max_drawdown
        },
        "mode_performance": mode_performance,
        "portfolio": {
            "value": portfolio_value,
            "equity": equity
        },
        "open_positions": open_positions,
        "models_status": {
            "normal": {
                "trained": bot.researcher.model_normal is not None,
                "status": "LIVE/LAYAK" if bot.supervisor.is_normal_valid() else "IDLE/QUARANTINE",
                "is_training": bot.researcher.is_training_normal,
                "last_accuracy": bot.researcher.last_accuracy_normal
            },
            "runner": {
                "trained": bot.researcher.model_runner is not None,
                "status": "LIVE/LAYAK" if bot.supervisor.is_runner_valid() else "IDLE/QUARANTINE",
                "is_training": bot.researcher.is_training_runner,
                "last_accuracy": bot.researcher.last_accuracy_runner
            }
        },
        "market_regime": getattr(bot.executor, 'current_market_regime', {"adx": 0.0, "regime": "UNKNOWN"}),
        "online_learning": {
            "enabled": Config.ENABLE_ONLINE_LEARNING,
            "last_retrain": getattr(bot.executor, 'last_micro_retrain_time', None)
        },
        "next_high_impact_news": next_high_impact_news,
        "risk_settings": {
            "mode": Config.RISK_MODE,
            "dollars": Config.MAX_RISK_DOLLARS,
            "percent": Config.MAX_RISK_PERCENT,
            "effective_dollars": round(
                Config.MAX_RISK_DOLLARS if Config.RISK_MODE == "dollars" else (equity * (Config.MAX_RISK_PERCENT / 100.0)),
                2
            )
        }
    }

class ModeRequest(BaseModel):
    mode: str

class RiskSettingRequest(BaseModel):
    risk_mode: str = "dollars" # "dollars" or "percent"
    risk_dollars: float = 10.0
    risk_percent: float = 1.0

class TrainRequest(BaseModel):
    mode: str
    type: str = "incremental"

class RLHFRequest(BaseModel):
    setup_id:    str
    symbol:      str
    action_type: str
    probability: float
    decision:    str  # "approve" | "reject" | "ignore"
    notes:       str = ""
    mode:        str = "normal"  # "normal" | "runner"

@app.get("/api/settings/risk")
async def get_risk_settings():
    account_info = mt5.account_info() if bot.mt5_connected else None
    equity = account_info.equity if account_info and account_info.equity > 0 else (account_info.balance if account_info else 1000.0)
    effective_dollars = Config.MAX_RISK_DOLLARS if Config.RISK_MODE == "dollars" else (equity * (Config.MAX_RISK_PERCENT / 100.0))
    return {
        "risk_mode": Config.RISK_MODE,
        "risk_dollars": Config.MAX_RISK_DOLLARS,
        "risk_percent": Config.MAX_RISK_PERCENT,
        "equity": round(equity, 2),
        "effective_dollars": round(effective_dollars, 2)
    }

@app.post("/api/settings/risk")
async def update_risk_settings(req: RiskSettingRequest):
    if req.risk_mode not in ["dollars", "percent"]:
        return {"status": "error", "message": "risk_mode must be 'dollars' or 'percent'"}
    
    if req.risk_dollars <= 0 or req.risk_percent <= 0:
        return {"status": "error", "message": "Risk value must be greater than 0"}

    Config.RISK_MODE = req.risk_mode
    Config.MAX_RISK_DOLLARS = float(req.risk_dollars)
    Config.MAX_RISK_PERCENT = float(req.risk_percent)

    account_info = mt5.account_info() if bot.mt5_connected else None
    equity = account_info.equity if account_info and account_info.equity > 0 else 1000.0
    effective = Config.MAX_RISK_DOLLARS if Config.RISK_MODE == "dollars" else (equity * (Config.MAX_RISK_PERCENT / 100.0))
    
    logging.info(f"[SETTINGS] Risk per trade diperbarui: Mode={Config.RISK_MODE}, ${Config.MAX_RISK_DOLLARS} / {Config.MAX_RISK_PERCENT}% (Eff: ${effective:.2f})")
    return {
        "status": "success",
        "message": f"Risk setting updated: {Config.RISK_MODE.upper()} (${Config.MAX_RISK_DOLLARS} / {Config.MAX_RISK_PERCENT}%)",
        "data": {
            "risk_mode": Config.RISK_MODE,
            "risk_dollars": Config.MAX_RISK_DOLLARS,
            "risk_percent": Config.MAX_RISK_PERCENT,
            "effective_dollars": round(effective, 2)
        }
    }

class ResetTradeRequest(BaseModel):
    targets: Optional[List[str]] = None

@app.post("/api/trades/reset")
async def reset_trades_endpoint(req: Optional[ResetTradeRequest] = None):
    try:
        from database import reset_ai_trade_history
        targets = req.targets if req and req.targets else None
        result = reset_ai_trade_history(targets)
        return {
            "status": "success",
            "message": "Data trading AI yang dipilih berhasil dibersihkan untuk Fresh Start.",
            "details": result
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/state/toggle")
async def toggle_state():
    bot.is_live = not bot.is_live
    if bot.is_live:
        bot.active_since = datetime.now().isoformat()
        if bot.mt5_connected:
            # FIX #8: Hanya validasi model yang sudah benar-benar dilatih
            normal_valid = bot.researcher.model_normal is not None
            runner_valid = bot.researcher.model_runner is not None
            if normal_valid or runner_valid:
                bot.supervisor.set_model_validity(normal_valid, runner_valid)
                if bot.supervisor.state != 'live':
                    bot.supervisor.force_start_live()
            else:
                logging.warning("[TOGGLE] Tidak ada model yang dilatih. Supervisor tidak distart. Latih model terlebih dahulu.")

        # FIX #2: Jalankan executor.monitor_market() sebagai asyncio background task
        if bot.executor_task is None or bot.executor_task.done():
            bot.executor.running = True
            bot.executor_task = asyncio.create_task(bot.executor.monitor_market())
            logging.info("✅ Executor Task berhasil dijalankan sebagai background coroutine.")
    else:
        # Hentikan executor saat dimatikan
        bot.executor.stop()
        if bot.executor_task and not bot.executor_task.done():
            bot.executor_task.cancel()
            bot.executor_task = None
        bot.active_since = None
    return {"status": "success", "is_live": bot.is_live, "mt5_connected": bot.mt5_connected}

@app.post("/api/state/emergency")
async def emergency_stop():
    # FIX #2: Cancel executor asyncio task jika berjalan
    bot.executor.stop()
    if bot.executor_task and not bot.executor_task.done():
        bot.executor_task.cancel()
        bot.executor_task = None
    bot.supervisor.trigger_friday_liquidator()
    from utils.mt5_utils import shutdown_mt5
    shutdown_mt5()
    bot.is_live = False
    bot.active_since = None
    logging.warning("🚨 EMERGENCY STOP TRIGGERED. All systems halted, MT5 disconnected.")
    return {"status": "success", "message": "Emergency Stop activated."}

@app.post("/api/strategies/force_live")
async def force_live(req: ModeRequest):
    bot.supervisor.force_live_mode(req.mode)
    if bot.supervisor.state == 'live':
        bot.is_live = True
    return {"status": "success", "mode": req.mode, "action": "force_live", "state": bot.supervisor.state}

@app.post("/api/strategies/quarantine")
async def quarantine(req: ModeRequest):
    bot.supervisor.isolate_quarantine(req.mode)
    return {"status": "success", "mode": req.mode, "action": "quarantine", "state": bot.supervisor.state}

class SyncDataRequest(BaseModel):
    force_rebuild: bool = False
    total_candles: Optional[int] = None

sync_state = {
    "is_syncing": False,
    "sync_type": None,  # "incremental" or "backfill"
    "progress": 0,
    "message": "Idle",
    "inserted_rows": 0,
    "last_synced_at": None,
    "error": None
}

@app.post("/api/data/sync")
async def sync_data_endpoint():
    """
    Sinkronisasi Cepat MT5 (Inkremental):
    HANYA menarik selisih candle baru sejak record terakhir dan me-append ke market_data_merged.
    TIDAK PERNAH men-drop database atau men-download 5 juta candle.
    """
    global sync_state
    if sync_state["is_syncing"]:
        return {"status": "busy", "message": "Proses sinkronisasi data sedang berjalan...", "sync_status": sync_state}
    
    if not bot.mt5_connected:
        bot.connect_mt5()
        if not bot.mt5_connected:
            return {"status": "error", "message": "Gagal terhubung ke MT5. Pastikan MetaTrader 5 aktif dan login broker valid."}

    def run_sync():
        global sync_state
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
            sync_state["inserted_rows"] = inserted
            sync_state["last_synced_at"] = datetime.now().isoformat()
            sync_state["message"] = msg
            sync_state["progress"] = 100
        except Exception as e:
            logging.error(f"Error during incremental sync: {e}")
            sync_state["error"] = str(e)
            sync_state["message"] = f"Gagal sinkronisasi: {e}"
        finally:
            sync_state["is_syncing"] = False

    threading.Thread(target=run_sync, daemon=True).start()
    return {
        "status": "success", 
        "message": "Sinkronisasi candle terbaru dari MT5 dimulai di background.",
        "sync_status": sync_state
    }

@app.post("/api/data/backfill")
async def force_backfill_endpoint():
    """
    Force Backfill (Rebuild):
    Men-drop tabel dan men-download ulang 5.000.000 candle secara penuh.
    """
    global sync_state
    if sync_state["is_syncing"]:
        return {"status": "busy", "message": "Proses sinkronisasi data sedang berjalan...", "sync_status": sync_state}
    
    if not bot.mt5_connected:
        bot.connect_mt5()
        if not bot.mt5_connected:
            return {"status": "error", "message": "Gagal terhubung ke MT5."}

    if bot.supervisor.state != 'ingestion':
        bot.supervisor.start_ingestion()

    def run_backfill():
        global sync_state
        sync_state["is_syncing"] = True
        sync_state["sync_type"] = "backfill"
        sync_state["progress"] = 0
        sync_state["message"] = "Memulai Force Backfill (Rebuild 5,000,000 candles)..."
        sync_state["error"] = None
        
        def progress_cb(current_b, total_b, cur, tot):
            sync_state["progress"] = int((current_b / max(1, total_b)) * 100)
            sync_state["message"] = f"Menyimpan batch {current_b}/{total_b} ({sync_state['progress']}%) ke database..."

        try:
            inserted = bot.data_miner.backfill_data(
                total_candles=5000000,
                progress_callback=progress_cb,
                force_rebuild=True
            )
            sync_state["inserted_rows"] = inserted
            sync_state["last_synced_at"] = datetime.now().isoformat()
            sync_state["message"] = f"Sukses Force Backfill: {inserted:,} candle tersimpan ke database."
            sync_state["progress"] = 100
        except Exception as e:
            logging.error(f"Error during backfill: {e}")
            sync_state["error"] = str(e)
            sync_state["message"] = f"Gagal backfill: {e}"
        finally:
            sync_state["is_syncing"] = False

    threading.Thread(target=run_backfill, daemon=True).start()
    return {
        "status": "success", 
        "message": "Force Backfill MT5 dimulai di background. Cek terminal logs.",
        "sync_status": sync_state
    }

@app.get("/api/data/sync/status")
async def get_sync_status():
    return sync_state

@app.get("/api/database/health")
async def get_database_health():
    try:
        from database import get_db_size, get_db_date_range
        row_count = get_db_size()
        min_date, max_date = get_db_date_range()

        mt5_latest_time = None
        if bot.mt5_connected:
            try:
                rates_last = mt5.copy_rates_from_pos(Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 1)
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
            "sync_status": sync_state
        }
    except Exception as e:
        logging.error(f"Failed to fetch database health: {e}")
        return {"status": "error", "message": str(e), "sync_status": sync_state}

@app.get("/api/macro/next-event")
async def get_next_macro_event():
    """Mengambil 1 berita High Impact terdekat untuk countdown di UI."""
    try:
        from database import get_next_high_impact_event
        if bot.data_miner is not None and bot.mt5_connected:
            bot.data_miner.get_live_calendar()
        ev = get_next_high_impact_event()
        return {"status": "success", "event": ev}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/macro/events")
async def get_upcoming_macro_events():
    """Mengambil daftar berita ekonomi mendatang dari database cache."""
    try:
        from database import get_upcoming_economic_events
        if bot.data_miner is not None and bot.mt5_connected:
            bot.data_miner.get_live_calendar()
        events = get_upcoming_economic_events(limit=15)
        return {"status": "success", "events": events}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/macro/sync")
async def sync_macro_events():
    """Memicu sinkronisasi paksa file CSV MacroBridge EA ke database."""
    try:
        if bot.data_miner is not None:
            df = bot.data_miner.sync_mt5_calendar_to_db()
            return {"status": "success", "synced_count": len(df)}
        return {"status": "error", "message": "DataMiner agent is unavailable"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/strategies/train")
async def train_model(req: TrainRequest):
    def _train_task():
        try:
            logging.info(f"Memulai pelatihan AI ({req.type}) untuk {req.mode} Mode...")

            # Gunakan load_train_chunks() dari data_miner dengan mode terisolasi agar Hard Negatives + RLHF diinjeksi tepat sasaran
            total_chunks, data_generator = bot.data_miner.load_train_chunks(chunk_size=5000, mode=req.mode)
            if total_chunks == 0 or data_generator is None:
                logging.warning("⚠️ Training dibatalkan: Database market_data kosong. Jalankan Force Backfill MT5 terlebih dahulu.")
                return
                
            # Load test chunks for Out-Of-Sample validation (>50%)
            total_test_chunks, test_generator = bot.data_miner.load_test_chunks(chunk_size=5000)

            if req.type == 'full':
                if req.mode == 'normal':
                    bot.researcher.model_normal = None
                    logging.info("[FULL TRAIN] Model Normal di-reset. Melatih dari awal...")
                elif req.mode == 'runner':
                    bot.researcher.model_runner = None
                    logging.info("[FULL TRAIN] Model Runner di-reset. Melatih dari awal...")

            if req.mode == 'normal':
                bot.researcher.is_training_normal = True
                try:
                    result = bot.researcher.train_normal_mode(data_generator, total_chunks=total_chunks)
                    if result:
                        if test_generator and total_test_chunks > 0:
                            accuracy = bot.gatekeeper.validate_model('normal', test_generator, total_test_chunks)
                            bot.researcher.last_accuracy_normal = float(accuracy)
                            bot.researcher.last_trained_normal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            bot.researcher.save_metadata()
                            if accuracy > 0.50:
                                bot.supervisor.set_model_validity(True, bot.supervisor.is_runner_valid())
                                logging.info("✅ Model Normal lulus validasi. Supervisor Normal Mode = VALID.")
                            else:
                                bot.supervisor.set_model_validity(False, bot.supervisor.is_runner_valid())
                                logging.warning("❌ Model Normal gagal validasi (<50%). Supervisor Normal Mode = QUARANTINE.")
                        else:
                            bot.supervisor.set_model_validity(True, bot.supervisor.is_runner_valid())
                            bot.researcher.last_trained_normal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            bot.researcher.save_metadata()
                            logging.info("✅ Model Normal dilatih tanpa OOS. Supervisor Normal Mode = VALID.")
                finally:
                    bot.researcher.is_training_normal = False
            elif req.mode == 'runner':
                bot.researcher.is_training_runner = True
                try:
                    result = bot.researcher.train_runner_mode(data_generator, total_chunks=total_chunks)
                    if result:
                        if test_generator and total_test_chunks > 0:
                            accuracy = bot.gatekeeper.validate_model('runner', test_generator, total_test_chunks)
                            bot.researcher.last_accuracy_runner = float(accuracy)
                            bot.researcher.last_trained_runner = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            bot.researcher.save_metadata()
                            if accuracy > 0.50:
                                bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(), True)
                                logging.info("✅ Model Runner lulus validasi. Supervisor Runner Mode = VALID.")
                            else:
                                bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(), False)
                                logging.warning("❌ Model Runner gagal validasi (<50%). Supervisor Runner Mode = QUARANTINE.")
                        else:
                            bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(), True)
                            bot.researcher.last_trained_runner = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            bot.researcher.save_metadata()
                            logging.info("✅ Model Runner dilatih tanpa OOS. Supervisor Runner Mode = VALID.")
                finally:
                    bot.researcher.is_training_runner = False

            logging.info(f"✅ Pelatihan AI ({req.type}) untuk {req.mode} Mode selesai.")
        except Exception as e:
            import traceback
            logging.error(f"Training failed: {e}")
            logging.error(traceback.format_exc())

    threading.Thread(target=_train_task, daemon=True).start()
    return {"status": "success", "message": f"{req.type.capitalize()} Training {req.mode} mode started in background. Cek Logs untuk progress."}

class MicroTrainRequest(BaseModel):
    mode: str = "all" # "normal", "runner", or "all"

@app.post("/api/strategies/micro-train")
async def trigger_micro_train(req: MicroTrainRequest = None):
    """Memicu Online Learning Micro-Retrain secara on-demand / manual."""
    target_mode = req.mode.lower() if req and req.mode else "all"

    def _micro_task():
        try:
            logging.info(f"[API MICRO-TRAIN] Memulai Micro-Retrain on-demand untuk mode: {target_mode.upper()}...")
            df_recent = bot.data_miner.load_recent_micro_chunk(n_candles=3000)
            if df_recent is None or df_recent.empty:
                logging.warning("[API MICRO-TRAIN] Data candle recent kosong di database.")
                return

            if target_mode in ["normal", "all"] and bot.researcher.model_normal is not None:
                fb_normal = bot.data_miner.load_live_decision_chunk(mode="normal")
                bot.researcher.micro_retrain("normal", df_recent, fb_normal)

            if target_mode in ["runner", "all"] and bot.researcher.model_runner is not None:
                fb_runner = bot.data_miner.load_live_decision_chunk(mode="runner")
                bot.researcher.micro_retrain("runner", df_recent, fb_runner)

            bot.executor.last_micro_retrain_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"✅ [API MICRO-TRAIN] Micro-Retrain selesai pada {bot.executor.last_micro_retrain_time}.")
        except Exception as e:
            logging.error(f"[API MICRO-TRAIN] Gagal: {e}")

    threading.Thread(target=_micro_task, daemon=True).start()
    return {"status": "success", "message": f"Online Micro-Retrain ({target_mode.upper()}) started in background. Cek Logs untuk progress."}

@app.post("/api/rlhf/feedback")
async def submit_rlhf(req: RLHFRequest):
    try:
        from database import save_approved_setup, save_rejected_setup, save_ignored_setup
        mode_val = req.mode.lower() if req.mode else "normal"
        logging.info(f"Menerima RLHF Feedback: {req.decision.upper()} [{mode_val.upper()}] untuk {req.setup_id}")
        if req.decision == "approve":
            save_approved_setup(req.setup_id, req.symbol, req.action_type, req.probability, req.notes, mode=mode_val)
        elif req.decision == "reject":
            save_rejected_setup(req.setup_id, req.symbol, req.action_type, req.probability, req.notes, mode=mode_val)
        elif req.decision == "ignore":
            save_ignored_setup(req.setup_id, req.symbol, req.action_type, req.probability, req.notes, mode=mode_val)
        else:
            return {"status": "error", "message": f"Decision tidak valid: {req.decision}. Gunakan approve/reject/ignore."}
        return {"status": "success", "message": f"Setup {req.setup_id} marked as {req.decision} ({mode_val})."}
    except Exception as e:
        logging.error(f"RLHF error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/rlhf/setups")
async def get_rlhf_setups(min_prob: float = 0.65, offset: int = 0, mode: str = "normal"):
    """
    Review Queue: Kembalikan 1 setup OOS per request berdasarkan offset dan mode (normal vs runner).
    Tiap setup dilengkapi candle M5/M15 (resample dari M1), SL/TP dinamis, dan deteksi outcome nyata.
    """
    try:
        import pandas as pd
        from database import sync_engine
        mode_str = mode.lower() if mode else "normal"

        # --- 1. Ambil seluruh OOS data (20% akhir database) ---
        query_count = "SELECT COUNT(*) FROM market_data_merged"
        total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
        if total_rows < 100:
            return {"status": "error", "message": "Database kosong. Jalankan Force Backfill MT5 terlebih dahulu.", "setup": None, "total": 0}

        split_idx = int(total_rows * 0.8)
        df_oos = pd.read_sql(
            f'SELECT time, open, high, low, close, "ATR_14" FROM market_data_merged ORDER BY time ASC OFFSET {split_idx}',
            con=sync_engine, index_col='time'
        )
        df_oos.index = pd.to_datetime(df_oos.index)

        if df_oos.empty or len(df_oos) < 50:
            return {"status": "error", "message": "Data OOS tidak cukup.", "setup": None, "total": 0}

        # --- 2. Prediksi probabilitas sesuai model mode yang dipilih ---
        target_model = bot.researcher.model_normal if mode_str == "normal" else bot.researcher.model_runner
        if target_model is not None:
            df_full_oos = pd.read_sql(
                f'SELECT * FROM market_data_merged ORDER BY time ASC OFFSET {split_idx}',
                con=sync_engine, index_col='time'
            )
            df_full_oos.index = pd.to_datetime(df_full_oos.index)
            df_full_oos = bot.researcher.generate_targets(df_full_oos)
            features   = bot.researcher.features
            valid_cols = [c for c in features if c in df_full_oos.columns]
            if valid_cols:
                probs = target_model.predict_proba(df_full_oos[valid_cols])[:, 1]
                df_oos['prob'] = probs
            else:
                df_oos['prob'] = np.random.uniform(0.5, 0.99, len(df_oos))
        else:
            np.random.seed(42 if mode_str == "normal" else 84)
            df_oos['prob'] = np.random.uniform(0.5, 0.99, len(df_oos))

        # --- 3. Filter prob >= min_prob, exclude yang sudah diproses untuk mode ini ---
        from database import get_approved_setup_ids, get_rejected_setup_ids, get_ignored_setup_ids
        processed = get_approved_setup_ids(mode=mode_str) | get_rejected_setup_ids(mode=mode_str) | get_ignored_setup_ids(mode=mode_str)

        high_prob = df_oos[df_oos['prob'] >= min_prob].copy()

        # Buat daftar kandidat (belum diproses), diurutkan dari terlama ke terbaru
        candidates = [
            idx for idx in high_prob.index
            if (idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, 'strftime') else str(idx)) not in processed
        ]
        total_pending = len(candidates)

        if total_pending == 0:
            return {"status": "done", "message": f"Semua setup OOS ({mode_str.upper()}) sudah dikurasi!", "setup": None, "total": 0, "current": 0}

        if offset >= total_pending:
            return {"status": "done", "message": "Sudah mencapai akhir antrian.", "setup": None, "total": total_pending, "current": offset}

        # --- 4. Ambil setup ke-N berdasarkan offset ---
        idx      = candidates[offset]
        row      = high_prob.loc[idx]
        setup_id = idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, 'strftime') else str(idx)

        # --- 5. Kalkulasi action, SL, TP (Normal = RR 1:2, Runner = RR 1:5) ---
        dist   = row.get('dist_Close_EMA50', 0) if 'dist_Close_EMA50' in row.index else 0
        action = "BUY" if dist >= 0 else "SELL"

        atr = float(row.get('ATR_14', 5.0)) if 'ATR_14' in row.index else 5.0
        if pd.isna(atr) or atr < 2.0:
            atr = 5.0
        price_val = float(row['close'])

        tp_multiplier = 2.0 if mode_str == "normal" else 5.0
        lookahead_candles = 100 if mode_str == "normal" else 300

        if action == "BUY":
            sl_val = round(price_val - atr, 2)
            tp_val = round(price_val + (atr * tp_multiplier), 2)
        else:
            sl_val = round(price_val + atr, 2)
            tp_val = round(price_val - (atr * tp_multiplier), 2)

        # Timeframe adaptif: M5 (scalping) atau M15 (jarak SL/TP jauh)
        tf_resample = "15min" if atr >= 10.0 else "5min"
        tf_label    = "M15"   if atr >= 10.0 else "M5"

        # --- 6. Slice M1, resample ke M5/M15 ---
        pos_in_oos = df_oos.index.get_loc(idx)
        start = max(0, pos_in_oos - 150)
        end   = min(len(df_oos), pos_in_oos + lookahead_candles + 100)

        slice_m1 = df_oos.iloc[start:end][['open', 'high', 'low', 'close']].copy()
        df_chart  = slice_m1.resample(tf_resample).agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna()

        candles_list = [
            {"time": int(ts.timestamp()), "open": float(r['open']),
             "high": float(r['high']), "low": float(r['low']), "close": float(r['close'])}
            for ts, r in df_chart.iterrows()
        ]

        # --- 7. Deteksi outcome dari M1 asli ---
        outcome  = "UNKNOWN"
        post_m1  = df_oos.iloc[pos_in_oos + 1: pos_in_oos + lookahead_candles][['high', 'low']]
        for _, pc in post_m1.iterrows():
            if action == "BUY":
                if pc['low']  <= sl_val: outcome = "SL_HIT"; break
                if pc['high'] >= tp_val: outcome = "TP_HIT"; break
            else:
                if pc['high'] >= sl_val: outcome = "SL_HIT"; break
                if pc['low']  <= tp_val: outcome = "TP_HIT"; break

        logging.info(f"[RLHF Queue {mode_str.upper()}] Offset {offset}/{total_pending}: {setup_id} | {action} | Prob: {row['prob']:.2f} | Outcome: {outcome} | TF: {tf_label}")

        return {
            "status":  "success",
            "mode":    mode_str,
            "total":   total_pending,
            "current": offset + 1,
            "setup": {
                "setup_id":      setup_id,
                "mode":          mode_str,
                "symbol":        Config.SYMBOL,
                "action":        action,
                "price":         price_val,
                "probability":   float(row['prob']),
                "time":          setup_id,
                "sl":            sl_val,
                "tp":            tp_val,
                "tp_multiplier": tp_multiplier,
                "outcome":       outcome,
                "candles":       candles_list,
                "entry_time":    int(idx.timestamp()),
                "tf_label":      tf_label
            }
        }
    except Exception as e:
        logging.error(f"Failed to fetch OOS review queue: {e}")
        import traceback
        logging.error(traceback.format_exc())
        return {"status": "error", "message": str(e), "setup": None, "total": 0}

@app.get("/api/journal")
async def get_journal(limit: int = 200, mode: str = None):
    try:
        from database import (
            sync_mt5_closed_deals_to_db,
            get_mt5_open_positions,
            get_trade_journal_entries,
            get_recent_trade_logs,
            get_trade_performance_summary,
            get_live_decision_summary
        )

        # 1. On-demand sync closed deals dari MT5 agar data selalu real dan ter-update
        try:
            sync_mt5_closed_deals_to_db(days_back=90)
        except Exception as e_sync:
            logging.debug(f"[Journal MT5 Sync] {e_sync}")

        # 2. Ambil posisi yang sedang aktif (floating) langsung dari MT5
        open_positions = get_mt5_open_positions()

        def clean_records(records):
            import math
            import pandas as pd
            cleaned = []
            for r in records:
                c_row = {}
                for k, v in r.items():
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        c_row[k] = None
                    elif pd.isna(v):
                        c_row[k] = None
                    elif hasattr(v, 'isoformat'):
                        c_row[k] = v.isoformat()
                    else:
                        c_row[k] = v
                cleaned.append(c_row)
            return cleaned

        # 3. Ambil Black Box XAI
        journal_df = get_trade_journal_entries(limit=limit)
        journal_data = clean_records(journal_df.to_dict(orient="records")) if not journal_df.empty else []
        
        # 4. Ambil Riwayat Trading PNL aktual (opsional filter mode)
        trade_logs = get_recent_trade_logs(limit=limit, mode=mode)
        trade_data = clean_records(trade_logs.to_dict(orient="records")) if not trade_logs.empty else []
        
        # 5. Ringkasan statistik performa per mode
        perf_summary = get_trade_performance_summary()

        # 6. Ringkasan Live Decision Feedback Loop (WIN/LOSS)
        live_feedback_summary = get_live_decision_summary()

        return {
            "status": "success",
            "open_positions": open_positions,
            "journal": journal_data,
            "trade_logs": trade_data,
            "performance": perf_summary,
            "live_feedback": live_feedback_summary
        }
    except Exception as e:
        logging.error(f"Failed to fetch trade journal: {e}")
        return {"status": "error", "open_positions": [], "journal": [], "trade_logs": [], "performance": {}, "live_feedback": {}}

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

TF_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

@app.get("/api/market/candles")
async def get_market_candles(timeframe: str = "M1", count: int = 200):
    tf_upper = timeframe.upper()
    tf_const = TIMEFRAME_MAP.get(tf_upper, mt5.TIMEFRAME_M1)
    
    if bot.mt5_connected:
        try:
            rates = mt5.copy_rates_from_pos(Config.SYMBOL, tf_const, 0, count)
            if rates is not None and len(rates) > 0:
                candles = [
                    {
                        "time": int(c['time']),
                        "open": float(c['open']),
                        "high": float(c['high']),
                        "low": float(c['low']),
                        "close": float(c['close'])
                    }
                    for c in rates
                ]
                return {"status": "success", "timeframe": tf_upper, "candles": candles}
        except Exception as e:
            logging.warning(f"Failed to fetch MT5 rates for tf {tf_upper}: {e}")

    # Fallback / mock data
    sec = TF_SECONDS.get(tf_upper, 60)
    mock_candles = []
    base_time = int(datetime.now().timestamp()) - (count * sec)
    base_price = 4028.75
    for i in range(count):
        chg = random.uniform(-1.5, 1.5)
        o = base_price
        c = base_price + chg
        h = max(o, c) + random.uniform(0, 0.5)
        lo = min(o, c) - random.uniform(0, 0.5)
        mock_candles.append({
            "time": base_time + i * sec,
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(lo, 2),
            "close": round(c, 2)
        })
        base_price = c
    return {"status": "success", "timeframe": tf_upper, "candles": mock_candles}

@app.websocket("/ws/market_data")
async def websocket_endpoint(websocket: WebSocket, timeframe: str = "M1"):
    await manager_market.connect(websocket)
    tf_upper = timeframe.upper()
    tf_const = TIMEFRAME_MAP.get(tf_upper, mt5.TIMEFRAME_M1)
    sec = TF_SECONDS.get(tf_upper, 60)
    try:
        # Kirim 200 candle historis saat client baru connect
        if bot.mt5_connected:
            try:
                rates_hist = mt5.copy_rates_from_pos(Config.SYMBOL, tf_const, 0, 200)
                if rates_hist is not None and len(rates_hist) > 0:
                    historical_candles = [
                        {
                            "time": int(c['time']),
                            "open": float(c['open']),
                            "high": float(c['high']),
                            "low": float(c['low']),
                            "close": float(c['close'])
                        }
                        for c in rates_hist
                    ]
                    await websocket.send_text(json.dumps({"type": "history", "timeframe": tf_upper, "data": historical_candles}))
                    logging.info(f"[WS] Mengirim {len(historical_candles)} candle historis ({tf_upper}) ke client.")
            except Exception as e:
                logging.warning(f"[WS] Gagal kirim historical candles: {e}")
        else:
            mock_candles = []
            base_time = int(datetime.now().timestamp()) - (200 * sec)
            base_price = 4028.75
            for i in range(200):
                chg = random.uniform(-1.5, 1.5)
                o = base_price
                c = base_price + chg
                h = max(o, c) + random.uniform(0, 0.5)
                lo = min(o, c) - random.uniform(0, 0.5)
                mock_candles.append({"time": base_time + i * sec, "open": round(o, 2), "high": round(h, 2), "low": round(lo, 2), "close": round(c, 2)})
                base_price = c
            await websocket.send_text(json.dumps({"type": "history", "timeframe": tf_upper, "data": mock_candles}))

        current_close = 4028.75
        current_time = int(datetime.now().timestamp())

        while True:
            if bot.is_live:
                if bot.mt5_connected:
                    try:
                        rates = mt5.copy_rates_from_pos(Config.SYMBOL, tf_const, 0, 1)
                        if rates is not None and len(rates) > 0:
                            candle = rates[0]
                            tick_data = {
                                "time": int(candle['time']),
                                "open": float(candle['open']),
                                "high": float(candle['high']),
                                "low": float(candle['low']),
                                "close": float(candle['close'])
                            }
                            await websocket.send_text(json.dumps({"type": "candle", "timeframe": tf_upper, "data": tick_data}))
                    except Exception:
                        pass
                else:
                    price_change = random.uniform(-2.0, 2.0)
                    current_close += price_change
                    current_time += sec
                    tick_data = {
                        "time": current_time,
                        "open": round(current_close - price_change, 2),
                        "high": round(max(current_close, current_close - price_change) + random.uniform(0, 1), 2),
                        "low": round(min(current_close, current_close - price_change) - random.uniform(0, 1), 2),
                        "close": round(current_close, 2)
                    }
                    await websocket.send_text(json.dumps({"type": "candle", "timeframe": tf_upper, "data": tick_data}))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager_market.disconnect(websocket)

@app.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket):
    await manager_logs.connect(websocket)
    try:
        while True:
            await asyncio.sleep(1) # Keep connection open
    except WebSocketDisconnect:
        manager_logs.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    # Mematikan reload=True karena statreload uvicorn akan memantau folder venv dan menyebabkan [WinError 1450]
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
