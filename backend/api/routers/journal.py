import math
import random
import logging
import asyncio
from datetime import datetime
import pandas as pd
from fastapi import APIRouter
import MetaTrader5 as mt5

from config import Config
from ..dependencies import bot

router = APIRouter(tags=["Journal & Market Candles"])

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

def clean_records(records):
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

@router.get("/api/journal")
async def get_journal(limit: int = 200, mode: str = None):
    """
    P0-1: Async journal fetching without blocking the event loop.
    """
    def _fetch_journal():
        from database import (
            sync_mt5_closed_deals_to_db,
            get_mt5_open_positions,
            get_trade_journal_entries,
            get_recent_trade_logs,
            get_trade_performance_summary,
            get_live_decision_summary
        )

        try:
            sync_mt5_closed_deals_to_db(days_back=90)
        except Exception as e_sync:
            logging.debug(f"[Journal MT5 Sync] {e_sync}")

        open_positions = get_mt5_open_positions()
        journal_df = get_trade_journal_entries(limit=limit)
        journal_data = clean_records(journal_df.to_dict(orient="records")) if not journal_df.empty else []
        
        trade_logs = get_recent_trade_logs(limit=limit, mode=mode)
        trade_data = clean_records(trade_logs.to_dict(orient="records")) if not trade_logs.empty else []
        
        perf_summary = get_trade_performance_summary()
        live_feedback_summary = get_live_decision_summary()

        return {
            "status": "success",
            "open_positions": open_positions,
            "journal": journal_data,
            "trade_logs": trade_data,
            "performance": perf_summary,
            "live_feedback": live_feedback_summary
        }

    try:
        return await asyncio.to_thread(_fetch_journal)
    except Exception as e:
        logging.error(f"Failed to fetch trade journal: {e}")
        return {"status": "error", "open_positions": [], "journal": [], "trade_logs": [], "performance": {}, "live_feedback": {}}

@router.get("/api/market/candles")
async def get_market_candles(timeframe: str = "M1", count: int = 200):
    tf_upper = timeframe.upper()
    tf_const = TIMEFRAME_MAP.get(tf_upper, mt5.TIMEFRAME_M1)
    
    if bot.mt5_connected:
        try:
            rates = await asyncio.to_thread(mt5.copy_rates_from_pos, Config.SYMBOL, tf_const, 0, count)
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
