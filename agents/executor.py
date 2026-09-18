import asyncio
import logging
import datetime
from config import Config
from utils.mt5_utils import check_spread
import MetaTrader5 as mt5

logging.basicConfig(level=logging.INFO)

class ExecutorAgent:
    """
    Agent 4: The Executor (Context-Aware Risk Manager)
    """
    
    def __init__(self, supervisor_agent):
        self.supervisor = supervisor_agent
        self.running = False
        
    async def monitor_market(self):
        self.running = True
        logging.info("Executor Agent started monitoring market...")
        logging.info(f"Circuit Breakers Active [SpreadLimit: {Config.SPREAD_LIMIT_POINTS}, MaxDD: {Config.MAX_DRAWDOWN_PERCENT}%, FridayLiquidator: ON]")
        
        while self.running:
            if self.supervisor.state != 'live':
                await asyncio.sleep(1)
                continue
                
            # Cek Friday Liquidator
            now = datetime.datetime.now()
            if now.weekday() == 4 and now.hour >= 23:
                logging.warning("[SEKRING] Friday Liquidator Active! Closing all positions.")
                self.supervisor.trigger_friday_liquidator()
                # logika close all via MT5
                await asyncio.sleep(60) 
                continue
                
            # Cek status sekring Spread
            spread = check_spread(Config.SYMBOL)
            if spread is not None and spread > Config.SPREAD_LIMIT_POINTS:
                logging.warning(f"[SEKRING] Eksekusi ditolak: Spread {spread} poin melebihi batas {Config.SPREAD_LIMIT_POINTS}")
                await asyncio.sleep(5)
                continue
                
            # Cek status sekring Drawdown
            account_info = mt5.account_info()
            if account_info is not None and account_info.balance > 0:
                dd_percent = (account_info.balance - account_info.equity) / account_info.balance
                if dd_percent > (Config.MAX_DRAWDOWN_PERCENT / 100.0):
                    logging.warning(f"[SEKRING] Max Drawdown {Config.MAX_DRAWDOWN_PERCENT}% REACHED! Equity: {account_info.equity}")
                    self.supervisor.trigger_max_drawdown()
                    continue

            # Simulasi delay tick
            await asyncio.sleep(1)

    def stop(self):
        self.running = False
        logging.info("Executor Agent stopped.")
        
    def execute_order(self, action, sl_distance):
        point_value = 1.0 
        sl_distance = max(sl_distance, 1.0)
        lot = Config.MAX_RISK_DOLLARS / (sl_distance * point_value)
        logging.info(f"Executing {action} order with {lot:.2f} Lot.")
