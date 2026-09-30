from .connection import (
    engine,
    sync_engine,
    AsyncSessionLocal,
    Base,
    Session,
)
from .models.market import MarketData
from .models.trade import TradeLog, LiveDecisionSample, TradeJournal
from .models.rlhf import ApprovedSetup, RejectedSetup, IgnoredSetup, HardNegative
from .models.macro import EconomicEvent
from .models.scorecard import ModelScorecard
from .migrations import ensure_schema_migrations

from .repositories.market_repo import (
    get_market_table_name,
    get_db_size,
    get_db_date_range,
    fetch_historical_data_chunks,
)
from .repositories.trade_repo import (
    log_trade_record,
    save_live_decision_sample,
    update_live_decision_outcome,
    get_live_decision_samples_for_training,
    get_recent_trade_logs,
    get_live_decision_summary,
    get_historical_pnl_feedback,
    get_trade_performance_summary,
    get_mt5_open_positions,
    sync_mt5_closed_deals_to_db,
    log_trade_journal,
    get_trade_journal_entries,
)
from .repositories.macro_repo import (
    save_macro_data,
    get_macro_data,
    get_next_high_impact_event,
    get_upcoming_economic_events,
)
from .repositories.rlhf_repo import (
    save_approved_setup,
    get_approved_setup_ids,
    get_all_approved_setups,
    save_rejected_setup,
    get_rejected_setup_ids,
    save_ignored_setup,
    get_ignored_setup_ids,
    add_hard_negative,
    bulk_add_hard_negatives,
    get_hard_negative_ids,
    get_rlhf_curation_stats,
    reset_ai_trade_history,
)
from .repositories.scorecard_repo import (
    save_scorecard_record,
    get_scorecard_history,
    get_latest_scorecards,
    delete_scorecards_by_symbol,
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    import asyncio
    await asyncio.to_thread(ensure_schema_migrations)

__all__ = [
    "engine",
    "sync_engine",
    "AsyncSessionLocal",
    "Base",
    "Session",
    "MarketData",
    "TradeLog",
    "LiveDecisionSample",
    "ApprovedSetup",
    "RejectedSetup",
    "IgnoredSetup",
    "HardNegative",
    "TradeJournal",
    "EconomicEvent",
    "init_db",
    "ensure_schema_migrations",
    "get_market_table_name",
    "get_db_size",
    "get_db_date_range",
    "fetch_historical_data_chunks",
    "log_trade_record",
    "save_live_decision_sample",
    "update_live_decision_outcome",
    "get_live_decision_samples_for_training",
    "get_recent_trade_logs",
    "get_live_decision_summary",
    "get_historical_pnl_feedback",
    "get_trade_performance_summary",
    "get_mt5_open_positions",
    "sync_mt5_closed_deals_to_db",
    "log_trade_journal",
    "get_trade_journal_entries",
    "save_macro_data",
    "get_macro_data",
    "get_next_high_impact_event",
    "get_upcoming_economic_events",
    "save_approved_setup",
    "get_approved_setup_ids",
    "get_all_approved_setups",
    "save_rejected_setup",
    "get_rejected_setup_ids",
    "save_ignored_setup",
    "get_ignored_setup_ids",
    "add_hard_negative",
    "bulk_add_hard_negatives",
    "get_hard_negative_ids",
    "get_rlhf_curation_stats",
    "reset_ai_trade_history",
    "ModelScorecard",
    "save_scorecard_record",
    "get_scorecard_history",
    "get_latest_scorecards",
]

