import os
import logging
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from config import Config

router = APIRouter(tags=["Risk & Settings"])

class RiskSettingsRequest(BaseModel):
    risk_mode: Optional[str] = None # "fixed", "dollars", atau "percent"
    fixed_lot_size: Optional[float] = None
    max_risk_dollars: Optional[float] = None
    max_risk_percent: Optional[float] = None
    max_lot_cap: Optional[float] = None
    ai_entry_threshold: Optional[float] = None

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
        "ai_entry_threshold": getattr(Config, 'AI_NORMAL_ENTRY_THRESHOLD', 75.0),
        "max_drawdown_percent": getattr(Config, 'MAX_DRAWDOWN_PERCENT', 30.0),
        "spread_limit_points": getattr(Config, 'SPREAD_LIMIT_POINTS', 400),
        "news_blackout_minutes": getattr(Config, 'NEWS_BLACKOUT_MINUTES', 15),
    }

@router.post("/api/settings/risk")
async def update_risk_settings(req: RiskSettingsRequest):
    if req.risk_mode is not None:
        Config.RISK_MODE = str(req.risk_mode).lower()
        os.environ["RISK_MODE"] = Config.RISK_MODE
    if req.fixed_lot_size is not None:
        Config.FIXED_LOT_SIZE = max(0.01, float(req.fixed_lot_size))
        os.environ["FIXED_LOT_SIZE"] = str(Config.FIXED_LOT_SIZE)
    if req.max_risk_dollars is not None:
        Config.MAX_RISK_DOLLARS = max(1.0, float(req.max_risk_dollars))
        os.environ["MAX_RISK_DOLLARS"] = str(Config.MAX_RISK_DOLLARS)
    if req.max_risk_percent is not None:
        Config.MAX_RISK_PERCENT = max(0.1, float(req.max_risk_percent))
        os.environ["MAX_RISK_PERCENT"] = str(Config.MAX_RISK_PERCENT)
    if req.max_lot_cap is not None:
        Config.MAX_LOT_CAP = max(0.01, float(req.max_lot_cap))
        os.environ["MAX_LOT_CAP"] = str(Config.MAX_LOT_CAP)
    if req.ai_entry_threshold is not None:
        Config.AI_NORMAL_ENTRY_THRESHOLD = max(50.0, min(95.0, float(req.ai_entry_threshold)))
        os.environ["AI_NORMAL_ENTRY_THRESHOLD"] = str(Config.AI_NORMAL_ENTRY_THRESHOLD)
    
    try:
        from dotenv import find_dotenv, set_key
        dotenv_path = find_dotenv()
        if dotenv_path:
            if req.risk_mode is not None:
                set_key(dotenv_path, "RISK_MODE", Config.RISK_MODE)
            if req.fixed_lot_size is not None:
                set_key(dotenv_path, "FIXED_LOT_SIZE", str(Config.FIXED_LOT_SIZE))
            if req.max_risk_dollars is not None:
                set_key(dotenv_path, "MAX_RISK_DOLLARS", str(Config.MAX_RISK_DOLLARS))
            if req.max_risk_percent is not None:
                set_key(dotenv_path, "MAX_RISK_PERCENT", str(Config.MAX_RISK_PERCENT))
            if req.max_lot_cap is not None:
                set_key(dotenv_path, "MAX_LOT_CAP", str(Config.MAX_LOT_CAP))
            if req.ai_entry_threshold is not None:
                set_key(dotenv_path, "AI_NORMAL_ENTRY_THRESHOLD", str(Config.AI_NORMAL_ENTRY_THRESHOLD))
    except Exception as env_err:
        logging.warning(f"Could not write settings to .env: {env_err}")

    # Format log khusus parameter aktif agar tidak membingungkan
    active_mode = getattr(Config, 'RISK_MODE', 'fixed').lower()
    if active_mode == "fixed":
        active_risk_str = f"Fixed Lot: {Config.FIXED_LOT_SIZE}"
    elif active_mode == "dollars":
        active_risk_str = f"Max Dollars: ${Config.MAX_RISK_DOLLARS}"
    elif active_mode == "percent":
        active_risk_str = f"Max Percent: {Config.MAX_RISK_PERCENT}%"
    else:
        active_risk_str = f"Fixed Lot: {Config.FIXED_LOT_SIZE}"

    logging.info(
        f"[SETTINGS UPDATE] Risk Mode: {active_mode} | {active_risk_str} | "
        f"Cap: {Config.MAX_LOT_CAP} | AI Threshold: {Config.AI_NORMAL_ENTRY_THRESHOLD}%"
    )
    return {
        "status": "success",
        "risk_mode": Config.RISK_MODE,
        "fixed_lot_size": Config.FIXED_LOT_SIZE,
        "max_risk_dollars": Config.MAX_RISK_DOLLARS,
        "max_risk_percent": Config.MAX_RISK_PERCENT,
        "max_lot_cap": Config.MAX_LOT_CAP,
        "ai_entry_threshold": Config.AI_NORMAL_ENTRY_THRESHOLD
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
