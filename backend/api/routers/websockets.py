import json
import random
import logging
import asyncio
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import MetaTrader5 as mt5

from config import Config
from ..dependencies import bot, manager_market, manager_logs

router = APIRouter(tags=["WebSockets"])

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

@router.websocket("/ws/market_data")
async def websocket_endpoint(websocket: WebSocket, timeframe: str = "M1", symbol: str = "XAUUSD"):
    await manager_market.connect(websocket)
    tf_upper = timeframe.upper()
    tf_const = TIMEFRAME_MAP.get(tf_upper, mt5.TIMEFRAME_M1)
    sec = TF_SECONDS.get(tf_upper, 60)

    from utils.mt5_utils import resolve_broker_symbol
    clean_sym = symbol.strip().upper() if symbol else "XAUUSD"
    broker_sym = resolve_broker_symbol(clean_sym)
    base_price = 1.0850 if "EUR" in clean_sym else (65000.0 if "BTC" in clean_sym else 4028.75)

    try:
        # Kirim 200 candle historis saat client baru connect
        if bot.mt5_connected:
            try:
                rates_hist = await asyncio.to_thread(mt5.copy_rates_from_pos, broker_sym, tf_const, 0, 200)
                if rates_hist is not None and len(rates_hist) > 0:
                    historical_candles = [
                        {
                            "time": int(c['time']),
                            "open": float(c['open']),
                            "high": float(c['high']),
                            "low": float(c['low']),
                            "close": float(c['close'])
                        }
                        for c in rates_hist
                    ]
                    await websocket.send_text(json.dumps({"type": "history", "symbol": clean_sym, "timeframe": tf_upper, "data": historical_candles}))
                    logging.info(f"[WS] Mengirim {len(historical_candles)} candle historis {clean_sym} [{broker_sym}] ({tf_upper}) ke client.")
            except Exception as e:
                logging.warning(f"[WS] Gagal kirim historical candles: {e}")
        else:
            mock_candles = []
            base_time = int(datetime.now().timestamp()) - (200 * sec)
            curr_p = base_price
            for i in range(200):
                chg = random.uniform(-0.0005, 0.0005) if base_price < 10 else random.uniform(-1.5, 1.5)
                o = curr_p
                c = curr_p + chg
                h = max(o, c) + (random.uniform(0, 0.0002) if base_price < 10 else random.uniform(0, 0.5))
                lo = min(o, c) - (random.uniform(0, 0.0002) if base_price < 10 else random.uniform(0, 0.5))
                mock_candles.append({
                    "time": base_time + i * sec,
                    "open": round(o, 5 if base_price < 10 else 2),
                    "high": round(h, 5 if base_price < 10 else 2),
                    "low": round(lo, 5 if base_price < 10 else 2),
                    "close": round(c, 5 if base_price < 10 else 2)
                })
                curr_p = c
            await websocket.send_text(json.dumps({"type": "history", "symbol": clean_sym, "timeframe": tf_upper, "data": mock_candles}))

        current_close = base_price
        current_time = int(datetime.now().timestamp())

        while True:
            if bot.mt5_connected:
                try:
                    rates = await asyncio.to_thread(mt5.copy_rates_from_pos, broker_sym, tf_const, 0, 1)
                    if rates is not None and len(rates) > 0:
                        candle = rates[0]
                        tick_data = {
                            "time": int(candle['time']),
                            "open": float(candle['open']),
                            "high": float(candle['high']),
                            "low": float(candle['low']),
                            "close": float(candle['close'])
                        }
                        await websocket.send_text(json.dumps({"type": "candle", "symbol": clean_sym, "timeframe": tf_upper, "data": tick_data}))
                except Exception:
                    pass
            else:
                price_change = random.uniform(-0.0002, 0.0002) if base_price < 10 else random.uniform(-2.0, 2.0)
                current_close += price_change
                current_time += sec
                tick_data = {
                    "time": current_time,
                    "open": round(current_close - price_change, 5 if base_price < 10 else 2),
                    "high": round(max(current_close, current_close - price_change) + (random.uniform(0, 0.0001) if base_price < 10 else random.uniform(0, 1)), 5 if base_price < 10 else 2),
                    "low": round(min(current_close, current_close - price_change) - (random.uniform(0, 0.0001) if base_price < 10 else random.uniform(0, 1)), 5 if base_price < 10 else 2),
                    "close": round(current_close, 5 if base_price < 10 else 2)
                }
                await websocket.send_text(json.dumps({"type": "candle", "symbol": clean_sym, "timeframe": tf_upper, "data": tick_data}))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager_market.disconnect(websocket)

@router.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket):
    await manager_logs.connect(websocket)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        manager_logs.disconnect(websocket)
