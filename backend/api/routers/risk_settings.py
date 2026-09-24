import os
import logging
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from config import Config

router = APIRouter(tags=["Risk & Settings"])

class RiskSettingsRequest(BaseModel):
    risk_mode: str # "fixed", "dollars", atau "percent"
    fixed_lot_size: Optional[float] = 0.01
    max_risk_dollars: Optional[float] = 10.0
    max_risk_percent: Optional[float] = 1.0
    max_lot_cap: Optional[float] = 0.10

class ResetTradesRequest(BaseModel):
    categories: Optional[List[str]] = None

@router.get("/api/settings/risk")
async def get_risk_settings():
    return {
        "risk_mode": getattr(Config, 'RISK_MODE', 'fixed'),
        "fixed_lot_size": getattr(Config, 'FIXED_LOT_SIZE', 0.01),
        "max_risk_dollars": getattr(Config, 'MAX_RISK_DOLLARS', 10.0),
        "max_risk_percent": getattr(Config, 'MAX_RISK_PERCENT', 1.0),
        "max_lot_cap": getattr(Config, 'MAX_LOT_CAP', 0.10),
        "max_drawdown_percent": getattr(Config, 'MAX_DRAWDOWN_PERCENT', 30.0),
        "spread_limit_points": getattr(Config, 'SPREAD_LIMIT_POINTS', 400),
        "news_blackout_minutes": getattr(Config, 'NEWS_BLACKOUT_MINUTES', 15),
    }

@router.post("/api/settings/risk")
async def update_risk_settings(req: RiskSettingsRequest):
    Config.RISK_MODE = str(req.risk_mode).lower()
    if req.fixed_lot_size is not None:
        Config.FIXED_LOT_SIZE = max(0.01, float(req.fixed_lot_size))
    if req.max_risk_dollars is not None:
        Config.MAX_RISK_DOLLARS = max(1.0, float(req.max_risk_dollars))
    if req.max_risk_percent is not None:
        Config.MAX_RISK_PERCENT = max(0.1, float(req.max_risk_percent))
    if req.max_lot_cap is not None:
        Config.MAX_LOT_CAP = max(0.01, float(req.max_lot_cap))
    
    os.environ["RISK_MODE"] = Config.RISK_MODE
    os.environ["FIXED_LOT_SIZE"] = str(Config.FIXED_LOT_SIZE)
    os.environ["MAX_RISK_DOLLARS"] = str(Config.MAX_RISK_DOLLARS)
    os.environ["MAX_RISK_PERCENT"] = str(Config.MAX_RISK_PERCENT)
    os.environ["MAX_LOT_CAP"] = str(Config.MAX_LOT_CAP)
    
    logging.info(f"[SETTINGS UPDATE] Risk Mode: {Config.RISK_MODE} | Fixed Lot: {Config.FIXED_LOT_SIZE} | Max Dollars: ${Config.MAX_RISK_DOLLARS} | Max Percent: {Config.MAX_RISK_PERCENT}% | Cap: {Config.MAX_LOT_CAP}")
    return {
        "status": "success",
        "risk_mode": Config.RISK_MODE,
        "fixed_lot_size": Config.FIXED_LOT_SIZE,
        "max_risk_dollars": Config.MAX_RISK_DOLLARS,
        "max_risk_percent": Config.MAX_RISK_PERCENT,
        "max_lot_cap": Config.MAX_LOT_CAP
    }

@router.post("/api/trades/reset")
async def reset_trades(req: ResetTradesRequest = ResetTradesRequest()):
    try:
        from database import reset_ai_trade_history
        cleared = reset_ai_trade_history(categories=req.categories)
        logging.info(f"[API] History trade dibersihkan: {cleared}")
        return {"status": "success", "cleared_tables": cleared}
    except Exception as e:
        logging.error(f"[API] Gagal membersihkan trade logs: {e}")
        return {"status": "error", "message": str(e)}
