from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import asyncio
import random
from datetime import datetime
import json
import logging
import threading

# Import agents
from agents.supervisor import SupervisorAgent
from agents.data_miner import DataMinerAgent
from agents.researcher import ResearcherAgent
from agents.gatekeeper import GatekeeperAgent
from agents.executor import ExecutorAgent
from config import Config
from utils.mt5_utils import init_mt5

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI(title="AvantGarde Bot API", description="Backend API for AvantGarde Trading Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    def connect_mt5(self):
        try:
            if init_mt5(Config.MT5_SERVER, Config.MT5_LOGIN, Config.MT5_PASSWORD, Config.MT5_PATH):
                logging.info("Successfully connected to MT5.")
                self.mt5_connected = True
                self.executor.data_miner = self.data_miner
                self.executor.researcher = self.researcher
            else:
                logging.warning("Failed to connect to MT5. Running in mock/offline mode.")
                self.mt5_connected = False
        except Exception as e:
            logging.error(f"MT5 initialization error: {e}")
            self.mt5_connected = False

bot = BotState()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.get("/api/state")
async def get_state():
    return {
        "is_live": bot.is_live,
        "active_since": bot.active_since,
        "mt5_connected": bot.mt5_connected,
        "supervisor_state": bot.supervisor.state,
        "performance": {
            "win_rate": 52.0, # Placeholder
            "total_trades": 145, # Placeholder
            "avg_profit": 1.8, # Placeholder
            "max_drawdown": -4.2 # Placeholder
        },
        "portfolio": {
            "value": 10450.00, # Placeholder
            "daily_change_value": 1245.80, # Placeholder
            "daily_change_pct": 13.21 # Placeholder
        }
    }

class ModeRequest(BaseModel):
    mode: str # 'normal' or 'runner'

@app.post("/api/state/toggle")
async def toggle_state():
    bot.is_live = not bot.is_live
    if bot.is_live:
        bot.active_since = datetime.now().isoformat()
        if bot.mt5_connected and bot.supervisor.state != 'live':
            # Force supervisor to start if connected
            bot.supervisor.set_model_validity(True, True)
            bot.supervisor.force_start_live()
    return {"status": "success", "is_live": bot.is_live, "mt5_connected": bot.mt5_connected}

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

@app.websocket("/ws/market_data")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        current_price = 4028.75
        while True:
            if bot.is_live:
                price_change = random.uniform(-2.0, 2.0)
                current_price += price_change
                tick_data = {
                    "symbol": Config.SYMBOL if bot.mt5_connected else "ETH/USDT",
                    "price": round(current_price, 2),
                    "timestamp": datetime.now().isoformat()
                }
                await manager.broadcast(json.dumps({"type": "tick", "data": tick_data}))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    # Menggunakan string "main:app" dan reload=True agar uvicorn me-restart server otomatis saat ada perubahan kode (Hot Reload)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
