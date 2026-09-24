import os
import logging
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from config import Config

router = APIRouter(tags=["Risk & Settings"])

class RiskSettingsRequest(BaseModel):
    risk_mode: str # "dollars" atau "percent"
    max_risk_dollars: float
    max_risk_percent: float

class ResetTradesRequest(BaseModel):
    categories: Optional[List[str]] = None

@router.get("/api/settings/risk")
async def get_risk_settings():
    return {
        "risk_mode": getattr(Config, 'RISK_MODE', 'dollars'),
        "max_risk_dollars": getattr(Config, 'MAX_RISK_DOLLARS', 10.0),
        "max_risk_percent": getattr(Config, 'MAX_RISK_PERCENT', 1.0),
        "max_drawdown_percent": getattr(Config, 'MAX_DRAWDOWN_PERCENT', 30.0),
        "spread_limit_points": getattr(Config, 'SPREAD_LIMIT_POINTS', 400),
        "news_blackout_minutes": getattr(Config, 'NEWS_BLACKOUT_MINUTES', 15),
    }

@router.post("/api/settings/risk")
async def update_risk_settings(req: RiskSettingsRequest):
    Config.RISK_MODE = str(req.risk_mode).lower()
    Config.MAX_RISK_DOLLARS = float(req.max_risk_dollars)
    Config.MAX_RISK_PERCENT = float(req.max_risk_percent)
    
    os.environ["RISK_MODE"] = Config.RISK_MODE
    os.environ["MAX_RISK_DOLLARS"] = str(Config.MAX_RISK_DOLLARS)
    os.environ["MAX_RISK_PERCENT"] = str(Config.MAX_RISK_PERCENT)
    
    logging.info(f"[SETTINGS UPDATE] Risk Mode: {Config.RISK_MODE} | Max Dollars: ${Config.MAX_RISK_DOLLARS} | Max Percent: {Config.MAX_RISK_PERCENT}%")
    return {
        "status": "success",
        "risk_mode": Config.RISK_MODE,
        "max_risk_dollars": Config.MAX_RISK_DOLLARS,
        "max_risk_percent": Config.MAX_RISK_PERCENT
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
