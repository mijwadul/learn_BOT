import os
import json
import logging
import threading
import asyncio
from datetime import datetime
from typing import List, Optional
from fastapi import WebSocket
import MetaTrader5 as mt5

from config import Config
from utils.mt5_utils import init_mt5
from agents.supervisor import SupervisorAgent
from agents.data_miner import DataMinerAgent
from agents.researcher import ResearcherAgent
from agents.gatekeeper import GatekeeperAgent
from agents.executor import ExecutorAgent

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
main_loop: Optional[asyncio.AbstractEventLoop] = None
sync_lock = threading.Lock()

sync_state = {
    "is_syncing": False,
    "progress": 0,
    "status": "Idle",
    "error": None
}

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
            is_run_ok = self.researcher.last_accuracy_runner >= 0.25 if self.researcher.last_accuracy_runner > 0 else True
            self.supervisor.set_model_validity(is_norm_ok, is_run_ok)
            
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
                self.researcher.last_accuracy_runner >= 0.25
            )
            logging.info(f"✅ [STARTUP VALIDATION] Selesai. Akurasi tersimpan: Normal={self.researcher.last_accuracy_normal*100:.1f}%, Runner={self.researcher.last_accuracy_runner*100:.1f}%")
        except Exception as e:
            logging.error(f"[STARTUP VALIDATION] Gagal: {e}")

    def connect_mt5(self):
        try:
            if init_mt5(Config.MT5_SERVER, Config.MT5_LOGIN, Config.MT5_PASSWORD, Config.MT5_PATH):
                logging.info("Successfully connected to MT5.")
                self.mt5_connected = True

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
