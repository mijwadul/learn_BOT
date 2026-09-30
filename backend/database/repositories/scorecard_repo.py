import datetime
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..connection import sync_engine
from ..models.scorecard import ModelScorecard
from ..migrations import ensure_schema_migrations

logger = logging.getLogger("ScorecardRepo")

def save_scorecard_record(
    scorecard: Dict[str, Any],
    oos_start_date: Optional[datetime.datetime] = None,
    oos_end_date: Optional[datetime.datetime] = None,
    trained_at: Optional[datetime.datetime] = None
) -> Optional[int]:
    """Menyimpan entri evaluasi kuantitatif finansial VectorBT ke tabel model_scorecard."""
    try:
        ensure_schema_migrations()

        symbol = str(scorecard.get("symbol", "XAUUSD")).strip().upper()
        mode = str(scorecard.get("mode", "normal")).strip().lower()

        # Parsing trained_at / evaluated_at
        eval_time = trained_at
        if eval_time is None and scorecard.get("evaluated_at"):
            try:
                eval_time = datetime.datetime.strptime(scorecard["evaluated_at"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                eval_time = datetime.datetime.now()
        if eval_time is None:
            eval_time = datetime.datetime.now()

        metrics = scorecard.get("metrics", {})
        reasons = scorecard.get("reasons", [])
        failure_str = "; ".join(reasons) if isinstance(reasons, list) and reasons else (str(reasons) if reasons else None)

        record = ModelScorecard(
            symbol=symbol,
            mode=mode,
            trained_at=eval_time,
            total_trades=int(metrics.get("total_trades", 0)),
            win_rate=float(metrics.get("win_rate_pct", 0.0)),
            profit_factor=float(metrics.get("profit_factor", 0.0)),
            sharpe_ratio=float(metrics.get("sharpe_ratio", 0.0)),
            max_drawdown=float(metrics.get("max_drawdown_pct", 0.0)),
            total_return=float(metrics.get("total_return_pct", 0.0)),
            passed=bool(scorecard.get("passed", False)),
            failure_reason=failure_str,
            threshold_used=float(scorecard.get("threshold_used", 0.0)) if scorecard.get("threshold_used") is not None else None,
            oos_start_date=oos_start_date,
            oos_end_date=oos_end_date,
            created_at=datetime.datetime.now()
        )

        with Session(sync_engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(f"[SCORECARD DB] Berhasil menyimpan scorecard ID #{record.id} ({symbol} - {mode.upper()} - Passed: {record.passed}).")
            return record.id

    except Exception as e:
        logger.error(f"[SCORECARD DB] Gagal menyimpan entri scorecard ke database: {e}", exc_info=True)
        return None

def get_scorecard_history(
    symbol: str = "XAUUSD",
    mode: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) -> Dict[str, Any]:
    """Mengambil riwayat kronologis scorecard model dengan pagination."""
    try:
        ensure_schema_migrations()
        sym_clean = str(symbol or "XAUUSD").strip().upper()
        page = max(1, int(page))
        limit = max(1, min(100, int(limit)))
        offset = (page - 1) * limit

        with Session(sync_engine) as session:
            query = session.query(ModelScorecard).filter(ModelScorecard.symbol == sym_clean)
            if mode and mode.lower() not in ["all", ""]:
                query = query.filter(ModelScorecard.mode == mode.lower().strip())

            total = query.count()
            rows = query.order_by(desc(ModelScorecard.trained_at), desc(ModelScorecard.id)).offset(offset).limit(limit).all()

            items = []
            for r in rows:
                items.append({
                    "id": r.id,
                    "symbol": r.symbol,
                    "mode": r.mode,
                    "trained_at": r.trained_at.strftime("%Y-%m-%d %H:%M:%S") if r.trained_at else None,
                    "total_trades": r.total_trades,
                    "win_rate_pct": round(float(r.win_rate or 0.0), 2),
                    "profit_factor": round(float(r.profit_factor or 0.0), 2),
                    "sharpe_ratio": round(float(r.sharpe_ratio or 0.0), 2),
                    "max_drawdown_pct": round(float(r.max_drawdown or 0.0), 2),
                    "total_return_pct": round(float(r.total_return or 0.0), 2),
                    "passed": bool(r.passed),
                    "failure_reason": r.failure_reason,
                    "threshold_used": r.threshold_used,
                    "oos_start_date": r.oos_start_date.strftime("%Y-%m-%d %H:%M:%S") if r.oos_start_date else None,
                    "oos_end_date": r.oos_end_date.strftime("%Y-%m-%d %H:%M:%S") if r.oos_end_date else None,
                    "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
                })

            total_pages = (total + limit - 1) // limit if total > 0 else 1

            return {
                "status": "success",
                "symbol": sym_clean,
                "mode": mode,
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "items": items
            }

    except Exception as e:
        logger.error(f"[SCORECARD DB] Gagal mengambil riwayat scorecard ({symbol}): {e}")
        return {
            "status": "error",
            "symbol": symbol,
            "message": str(e),
            "page": page,
            "limit": limit,
            "total": 0,
            "total_pages": 1,
            "items": []
        }

def get_latest_scorecards(symbol: str = "XAUUSD") -> Dict[str, Any]:
    """Mengambil scorecard terkini untuk kedua mode ('normal' dan 'runner')."""
    try:
        ensure_schema_migrations()
        sym_clean = str(symbol or "XAUUSD").strip().upper()
        latest = {"normal": None, "runner": None}

        with Session(sync_engine) as session:
            for m in ["normal", "runner"]:
                r = session.query(ModelScorecard).filter(
                    ModelScorecard.symbol == sym_clean,
                    ModelScorecard.mode == m
                ).order_by(desc(ModelScorecard.trained_at), desc(ModelScorecard.id)).first()

                if r:
                    latest[m] = {
                        "id": r.id,
                        "symbol": r.symbol,
                        "mode": r.mode,
                        "trained_at": r.trained_at.strftime("%Y-%m-%d %H:%M:%S") if r.trained_at else None,
                        "total_trades": r.total_trades,
                        "win_rate_pct": round(float(r.win_rate or 0.0), 2),
                        "profit_factor": round(float(r.profit_factor or 0.0), 2),
                        "sharpe_ratio": round(float(r.sharpe_ratio or 0.0), 2),
                        "max_drawdown_pct": round(float(r.max_drawdown or 0.0), 2),
                        "total_return_pct": round(float(r.total_return or 0.0), 2),
                        "passed": bool(r.passed),
                        "failure_reason": r.failure_reason,
                        "threshold_used": r.threshold_used,
                        "oos_start_date": r.oos_start_date.strftime("%Y-%m-%d %H:%M:%S") if r.oos_start_date else None,
                        "oos_end_date": r.oos_end_date.strftime("%Y-%m-%d %H:%M:%S") if r.oos_end_date else None,
                        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
                    }

        # Fallback / Enrich dari models_metadata.json jika database belum memiliki entri atau butuh detail equity_curve
        try:
            from agents.research.model_manager import ModelManager
            loaded = ModelManager.load_models(sym_clean)
            json_scorecards = loaded.get("oos_scorecard", {})
            for m in ["normal", "runner"]:
                if latest[m] is None and json_scorecards.get(m):
                    latest[m] = json_scorecards[m]
                elif latest[m] is not None and json_scorecards.get(m):
                    if "equity_curve" in json_scorecards[m] and "equity_curve" not in latest[m]:
                        latest[m]["equity_curve"] = json_scorecards[m]["equity_curve"]
                    if "criteria" in json_scorecards[m] and "criteria" not in latest[m]:
                        latest[m]["criteria"] = json_scorecards[m]["criteria"]
                    if "checks" in json_scorecards[m] and "checks" not in latest[m]:
                        latest[m]["checks"] = json_scorecards[m]["checks"]
        except Exception as e_meta:
            logger.debug(f"Could not read metadata scorecard fallback: {e_meta}")

        return {
            "status": "success",
            "symbol": sym_clean,
            "latest": latest
        }

    except Exception as e:
        logger.error(f"[SCORECARD DB] Gagal mengambil latest scorecard ({symbol}): {e}")
        return {
            "status": "error",
            "symbol": symbol,
            "message": str(e),
            "latest": {"normal": None, "runner": None}
        }

def delete_scorecards_by_symbol(symbol: str) -> int:
    """Menghapus seluruh rekaman riwayat scorecard kuantitatif untuk symbol tertentu (Reset Otak)."""
    try:
        ensure_schema_migrations()
        sym_clean = str(symbol or "XAUUSD").strip().upper()
        with Session(sync_engine) as session:
            deleted_count = session.query(ModelScorecard).filter(ModelScorecard.symbol == sym_clean).delete()
            session.commit()
            logger.info(f"[SCORECARD DB] 🗑️ Berhasil menghapus {deleted_count} entri scorecard untuk {sym_clean}.")
            return deleted_count
    except Exception as e:
        logger.error(f"[SCORECARD DB] Gagal menghapus scorecard untuk {symbol}: {e}")
        return 0

