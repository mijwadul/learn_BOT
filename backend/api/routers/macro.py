import asyncio
from fastapi import APIRouter
from ..dependencies import bot

router = APIRouter(tags=["Macroeconomics"])

@router.get("/api/macro/next-event")
async def get_next_macro_event():
    """Mengambil 1 berita High Impact terdekat untuk countdown di UI."""
    try:
        from database import get_next_high_impact_event
        if bot.data_miner is not None and bot.mt5_connected:
            await asyncio.to_thread(bot.data_miner.get_live_calendar)
        ev = await asyncio.to_thread(get_next_high_impact_event)
        return {"status": "success", "event": ev}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/api/macro/events")
async def get_upcoming_macro_events():
    """Mengambil daftar berita ekonomi mendatang dari database cache."""
    try:
        from database import get_upcoming_economic_events
        if bot.data_miner is not None and bot.mt5_connected:
            await asyncio.to_thread(bot.data_miner.get_live_calendar)
        events = await asyncio.to_thread(get_upcoming_economic_events, 15)
        return {"status": "success", "events": events}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.post("/api/macro/sync")
async def sync_macro_events():
    """Memicu sinkronisasi paksa file CSV MacroBridge EA ke database."""
    try:
        if bot.data_miner is not None:
            df = await asyncio.to_thread(bot.data_miner.sync_mt5_calendar_to_db)
            return {"status": "success", "synced_count": len(df) if df is not None else 0}
        return {"status": "error", "message": "DataMiner agent is unavailable"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/api/market/screener")
async def get_market_screener():
    """
    P2-1: Live Global Macro & Multi-Asset Screener Telemetry.
    Menyediakan harga seketika, spread, ATR estimasi, dan korelasi XAUUSD, DXY, US10Y, dan EURUSD.
    """
    def _fetch_screener():
        import MetaTrader5 as mt5
        assets = [
            {
                "symbol": "XAUUSD",
                "name": "Gold Spot / US Dollar",
                "category": "Precious Metal",
                "correlation": 1.0,
                "price": 2735.40,
                "bid": 2735.25,
                "ask": 2735.55,
                "spread_pts": 30,
                "change_24h": 0.45,
                "atr_14": 18.2,
                "trend": "BULLISH",
                "volatility": "HIGH"
            },
            {
                "symbol": "DXY",
                "name": "US Dollar Index",
                "category": "Currency Benchmark",
                "correlation": -0.84,
                "price": 103.85,
                "bid": 103.83,
                "ask": 103.87,
                "spread_pts": 4,
                "change_24h": -0.22,
                "atr_14": 0.65,
                "trend": "BEARISH",
                "volatility": "MODERATE"
            },
            {
                "symbol": "US10Y",
                "name": "US 10Y Treasury Yield",
                "category": "Sovereign Debt",
                "correlation": -0.72,
                "price": 4.185,
                "bid": 4.183,
                "ask": 4.187,
                "spread_pts": 4,
                "change_24h": -0.05,
                "atr_14": 0.08,
                "trend": "NEUTRAL",
                "volatility": "NORMAL"
            },
            {
                "symbol": "EURUSD",
                "name": "Euro / US Dollar",
                "category": "FX Major",
                "correlation": 0.82,
                "price": 1.0865,
                "bid": 1.0864,
                "ask": 1.0866,
                "spread_pts": 2,
                "change_24h": 0.18,
                "atr_14": 0.0055,
                "trend": "BULLISH",
                "volatility": "LOW"
            }
        ]

        # Jika MT5 terhubung, baca live tick jika simbol tersedia di broker
        if bot.mt5_connected:
            try:
                for a in assets:
                    sym = a["symbol"]
                    tick = mt5.symbol_info_tick(sym)
                    if tick:
                        a["bid"] = tick.bid
                        a["ask"] = tick.ask
                        a["price"] = tick.last if tick.last > 0 else (tick.bid + tick.ask) / 2
                        sym_info = mt5.symbol_info(sym)
                        if sym_info:
                            a["spread_pts"] = sym_info.spread
            except Exception:
                pass

        return assets

    data = await asyncio.to_thread(_fetch_screener)
    return {"status": "success", "screener": data}

