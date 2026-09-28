import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from config import Config
try:
    from utils.settings_manager import settings_manager
except ImportError:
    from backend.utils.settings_manager import settings_manager

router = APIRouter(tags=["Risk & Settings"])

class RiskSettingsRequest(BaseModel):
    risk_mode: Optional[str] = None # "fixed", "dollars", atau "percent"
    fixed_lot_size: Optional[float] = None
    max_risk_dollars: Optional[float] = None
    max_risk_percent: Optional[float] = None
    max_lot_cap: Optional[float] = None
    ai_entry_threshold: Optional[float] = None
    ai_runner_entry_threshold: Optional[float] = None
    pairs: Optional[Dict[str, Any]] = None
    pair_overrides: Optional[Dict[str, Any]] = None

class PairSettingRequest(BaseModel):
    threshold: Optional[float] = None
    ai_normal_entry_threshold: Optional[float] = None
    ai_runner_entry_threshold: Optional[float] = None

class ResetTradesRequest(BaseModel):
    categories: Optional[List[str]] = None

@router.get("/api/settings/risk")
async def get_risk_settings():
    return {
        "risk_mode": settings_manager.get_setting("risk_mode", getattr(Config, 'RISK_MODE', 'fixed')),
        "fixed_lot_size": settings_manager.get_setting("fixed_lot_size", getattr(Config, 'FIXED_LOT_SIZE', 0.01)),
        "max_risk_dollars": settings_manager.get_setting("max_risk_dollars", getattr(Config, 'MAX_RISK_DOLLARS', 10.0)),
        "max_risk_percent": settings_manager.get_setting("max_risk_percent", getattr(Config, 'MAX_RISK_PERCENT', 1.0)),
        "max_lot_cap": settings_manager.get_setting("max_lot_cap", getattr(Config, 'MAX_LOT_CAP', 0.10)),
        "ai_entry_threshold": settings_manager.get_setting("ai_normal_entry_threshold", getattr(Config, 'AI_NORMAL_ENTRY_THRESHOLD', 75.0)),
        "ai_runner_entry_threshold": settings_manager.get_setting("ai_runner_entry_threshold", getattr(Config, 'AI_RUNNER_ENTRY_THRESHOLD', 55.0)),
        "pairs": settings_manager.get_setting("pairs", {}),
        "max_drawdown_percent": getattr(Config, 'MAX_DRAWDOWN_PERCENT', 30.0),
        "spread_limit_points": getattr(Config, 'SPREAD_LIMIT_POINTS', 400),
        "news_blackout_minutes": getattr(Config, 'NEWS_BLACKOUT_MINUTES', 15),
    }

@router.post("/api/settings/risk")
async def update_risk_settings(req: RiskSettingsRequest):
    updates: Dict[str, Any] = {}

    if req.risk_mode is not None:
        updates["risk_mode"] = str(req.risk_mode).lower()
    if req.fixed_lot_size is not None:
        updates["fixed_lot_size"] = max(0.01, float(req.fixed_lot_size))
    if req.max_risk_dollars is not None:
        updates["max_risk_dollars"] = max(1.0, float(req.max_risk_dollars))
    if req.max_risk_percent is not None:
        updates["max_risk_percent"] = max(0.1, float(req.max_risk_percent))
    if req.max_lot_cap is not None:
        updates["max_lot_cap"] = max(0.01, float(req.max_lot_cap))
    if req.ai_entry_threshold is not None:
        updates["ai_normal_entry_threshold"] = max(50.0, min(95.0, float(req.ai_entry_threshold)))
    if req.ai_runner_entry_threshold is not None:
        updates["ai_runner_entry_threshold"] = max(40.0, min(95.0, float(req.ai_runner_entry_threshold)))
    if req.pairs is not None:
        updates["pairs"] = req.pairs
    if req.pair_overrides is not None:
        updates["pair_overrides"] = req.pair_overrides

    # Simpan secara atomik ke bot_settings.json (.env tidak pernah disentuh)
    saved = settings_manager.update_settings(updates)
    Config.reload_settings()

    # Format log khusus parameter aktif agar informatif
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
        f"[SETTINGS UPDATE] Persisted to bot_settings.json | Risk Mode: {active_mode} | {active_risk_str} | "
        f"Cap: {Config.MAX_LOT_CAP} | AI Threshold: {Config.AI_NORMAL_ENTRY_THRESHOLD}%"
    )

    return {
        "status": "success",
        "risk_mode": Config.RISK_MODE,
        "fixed_lot_size": Config.FIXED_LOT_SIZE,
        "max_risk_dollars": Config.MAX_RISK_DOLLARS,
        "max_risk_percent": Config.MAX_RISK_PERCENT,
        "max_lot_cap": Config.MAX_LOT_CAP,
        "ai_entry_threshold": Config.AI_NORMAL_ENTRY_THRESHOLD,
        "ai_runner_entry_threshold": Config.AI_RUNNER_ENTRY_THRESHOLD,
        "pairs": saved.get("pairs", {}),
    }

@router.post("/api/settings/pairs/{symbol}")
async def update_pair_settings(symbol: str, req: PairSettingRequest):
    """Mendukung per-pair parameter override (misal threshold XAUUSD vs BTCUSD)."""
    overrides: Dict[str, Any] = {}
    if req.threshold is not None:
        overrides["threshold"] = req.threshold
        overrides["ai_normal_entry_threshold"] = req.threshold * 100.0 if (0.0 < req.threshold <= 1.0) else req.threshold
    if req.ai_normal_entry_threshold is not None:
        overrides["ai_normal_entry_threshold"] = req.ai_normal_entry_threshold
        if "threshold" not in overrides:
            overrides["threshold"] = req.ai_normal_entry_threshold
    if req.ai_runner_entry_threshold is not None:
        overrides["ai_runner_entry_threshold"] = req.ai_runner_entry_threshold

    saved = settings_manager.set_pair_override(symbol, overrides)
    Config.reload_settings()
    sym_clean = symbol.strip().upper()
    return {
        "status": "success",
        "symbol": sym_clean,
        "pair_settings": saved.get("pairs", {}).get(sym_clean, {}),
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
