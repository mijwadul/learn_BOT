import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
import MetaTrader5 as mt5

from config import Config
from ..dependencies import bot

router = APIRouter(tags=["Bot State"])

class ToggleStateRequest(BaseModel):
    live: Optional[bool] = None

class PositionActionRequest(BaseModel):
    ticket: int
    symbol: Optional[str] = None

@router.get("/api/state")
async def get_state():
    """
    P0-1: Non-Blocking Async Event Loop di FastAPI.
    Semua pemanggilan blocking I/O (Database & MT5) dibungkus asyncio.to_thread
    untuk mencegah drop connection pada WebSocket dan polling frontend.
    """
    win_rate, total_trades, avg_profit, max_drawdown = 0.0, 0, 0.0, 0.0
    mode_performance = {}
    
    # 1. Non-blocking Database Query via asyncio.to_thread
    try:
        from database import get_recent_trade_logs, get_trade_performance_summary
        mode_performance = await asyncio.to_thread(get_trade_performance_summary)
        logs_df = await asyncio.to_thread(get_recent_trade_logs, 100)
        if not logs_df.empty:
            total_trades = len(logs_df)
            wins = len(logs_df[logs_df['profit'] > 0])
            win_rate = round((wins / total_trades) * 100, 1) if total_trades > 0 else 0.0
            avg_profit = round(logs_df['profit'].mean(), 2)
    except Exception:
        pass
        
    open_positions = []
    portfolio_value = 10450.00
    equity = 10450.00
    
    # 2. Non-blocking MT5 Calls via asyncio.to_thread
    if bot.mt5_connected:
        try:
            acc = await asyncio.to_thread(mt5.account_info)
            if acc:
                portfolio_value = acc.balance
                equity = acc.equity
                
            positions = await asyncio.to_thread(mt5.positions_get, symbol=Config.SYMBOL)
            if positions:
                for p in positions:
                    open_positions.append({
                        "symbol": Config.SYMBOL,
                        "ticket": p.ticket,
                        "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                        "volume": p.volume,
                        "open_price": p.price_open,
                        "current_price": p.price_current,
                        "sl": getattr(p, "sl", 0.0),
                        "tp": getattr(p, "tp", 0.0),
                        "profit": p.profit
                    })
        except Exception:
            pass

    # Sinkronisasi metadata akurasi persisten jika perlu
    if (bot.researcher.last_accuracy_normal == 0.0 or bot.researcher.last_accuracy_runner == 0.0) and os.path.exists("models/models_metadata.json"):
        try:
            with open("models/models_metadata.json", "r") as _mf:
                _meta = json.load(_mf)
            if bot.researcher.last_accuracy_normal == 0.0:
                bot.researcher.last_accuracy_normal = float(_meta.get("normal", {}).get("last_accuracy", 0.0))
            if bot.researcher.last_accuracy_runner == 0.0:
                bot.researcher.last_accuracy_runner = float(_meta.get("runner", {}).get("last_accuracy", 0.0))
        except Exception:
            pass

    # Non-blocking Macro Countdown
    next_high_impact_news = None
    try:
        from database import get_next_high_impact_event
        if bot.data_miner is not None and bot.mt5_connected:
            await asyncio.to_thread(bot.data_miner.get_live_calendar)
        next_high_impact_news = await asyncio.to_thread(get_next_high_impact_event)
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
                "last_accuracy": bot.researcher.last_accuracy_normal,
                "last_trained": bot.researcher.last_trained_normal
            },
            "runner": {
                "trained": bot.researcher.model_runner is not None,
                "status": "LIVE/LAYAK" if bot.supervisor.is_runner_valid() else "IDLE/QUARANTINE",
                "is_training": bot.researcher.is_training_runner,
                "last_accuracy": bot.researcher.last_accuracy_runner,
                "last_trained": bot.researcher.last_trained_runner
            }
        },
        "market_regime": getattr(bot.executor, 'current_market_regime', {"adx": 0.0, "regime": "UNKNOWN"}),
        "latest_probabilities": getattr(bot.executor, 'latest_probs', {}),
        "next_high_impact_news": next_high_impact_news
    }

@router.post("/api/state/toggle")
async def toggle_state(req: Optional[ToggleStateRequest] = None):
    target_live = not bot.is_live if (req is None or req.live is None) else bool(req.live)
    if target_live and not bot.is_live:
        bot.is_live = True
        bot.active_since = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        bot.supervisor.state = 'live'
        
        if not bot.mt5_connected:
            bot.connect_mt5()
            
        if bot.executor_task is None or bot.executor_task.done():
            bot.executor_task = asyncio.create_task(bot.executor.monitor_market())
            
        logging.info("Trading Bot ACTIVATED (Live Mode)")
    elif not target_live and bot.is_live:
        bot.is_live = False
        bot.active_since = None
        bot.supervisor.state = 'idle'
        bot.executor.running = False
        if bot.executor_task:
            bot.executor_task.cancel()
        logging.info("Trading Bot DEACTIVATED (Idle Mode)")
        
    return {"status": "success", "is_live": bot.is_live, "active_since": bot.active_since}

@router.post("/api/positions/break-even")
async def position_break_even(req: PositionActionRequest):
    sym = req.symbol or Config.SYMBOL
    success = await asyncio.to_thread(bot.executor.order_router.modify_sl_to_break_even, req.ticket, sym)
    return {"status": "success" if success else "error", "ticket": req.ticket, "action": "break_even"}

@router.post("/api/positions/partial-close")
async def position_partial_close(req: PositionActionRequest):
    sym = req.symbol or Config.SYMBOL
    success = await asyncio.to_thread(bot.executor.order_router.execute_partial_close_50, req.ticket, sym)
    return {"status": "success" if success else "error", "ticket": req.ticket, "action": "partial_close_50"}

@router.post("/api/positions/close")
async def position_close(req: PositionActionRequest):
    sym = req.symbol or Config.SYMBOL
    success = await asyncio.to_thread(bot.executor.order_router.execute_full_close, req.ticket, "Manual UI Close", sym)
    return {"status": "success" if success else "error", "ticket": req.ticket, "action": "full_close"}

@router.post("/api/state/emergency")
async def emergency_stop():
    bot.is_live = False
    bot.active_since = None
    bot.supervisor.trigger_max_drawdown()
    bot.executor.running = False
    if bot.executor_task:
        bot.executor_task.cancel()
        
    closed_orders = 0
    if bot.mt5_connected:
        try:
            positions = await asyncio.to_thread(mt5.positions_get, symbol=Config.SYMBOL)
            if positions:
                for p in positions:
                    bot.executor.order_router.execute_full_close(p.ticket, "EMERGENCY_STOP", Config.SYMBOL)
                    closed_orders += 1
        except Exception as e:
            logging.error(f"Error during emergency liquidations: {e}")
            
    logging.warning("EMERGENCY STOP TRIGGERED: Bot halted and positions liquidated.")
    return {"status": "halted", "closed_positions": closed_orders}
