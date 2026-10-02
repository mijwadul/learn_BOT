import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import dependencies
from api.dependencies import WebSocketLogHandler, bot, manager_market, manager_logs, sync_state
from api.routers import (
    bot_state_router,
    risk_settings_router,
    strategies_router,
    data_sync_router,
    macro_router,
    rlhf_router,
    journal_router,
    websockets_router,
    pairs_router,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

@asynccontextmanager
async def lifespan(app: FastAPI):
    dependencies.main_loop = asyncio.get_running_loop()
    try:
        from database import init_db
        await init_db()
        logging.info("✅ [STARTUP] Database initialized & schema migrations completed.")
    except Exception as e:
        logging.warning(f"⚠️ [STARTUP] DB initialization deferred: {e}")

    yield

    # ─── Graceful Teardown ───────────────────────────────────────────
    logging.info("🛑 [SHUTDOWN] Memulai graceful shutdown...")

    # 1. Hentikan Executor Task (live trading loop)
    executor_task = getattr(bot, "executor_task", None)
    if executor_task and not executor_task.done():
        try:
            bot.executor.running = False
        except Exception:
            pass
        executor_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(executor_task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        logging.info("✅ [SHUTDOWN] Executor task dihentikan.")

    # 2. Tutup koneksi MetaTrader 5
    try:
        from utils.mt5_utils import shutdown_mt5
        shutdown_mt5()
        logging.info("✅ [SHUTDOWN] Koneksi MetaTrader5 ditutup.")
    except Exception as e:
        logging.warning(f"⚠️ [SHUTDOWN] MT5 shutdown gagal: {e}")

    # 3. Bersihkan pool koneksi SQLAlchemy (async engine)
    try:
        from database.connection import engine
        await engine.dispose()
        logging.info("✅ [SHUTDOWN] Pool koneksi database dibersihkan.")
    except Exception as e:
        logging.warning(f"⚠️ [SHUTDOWN] DB engine dispose gagal: {e}")

    logging.info("✅ [SHUTDOWN] Graceful shutdown selesai.")

app = FastAPI(
    title="AvantGarde Bot API", 
    description="Backend API for AvantGarde Trading Bot (Modular Institutional Architecture)",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom WebSocket Log Handler
ws_handler = WebSocketLogHandler()
ws_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(ws_handler)

# Include Modular Routers
app.include_router(bot_state_router)
app.include_router(risk_settings_router)
app.include_router(strategies_router)
app.include_router(data_sync_router)
app.include_router(macro_router)
app.include_router(rlhf_router)
app.include_router(journal_router)
app.include_router(websockets_router)
app.include_router(pairs_router)


if __name__ == "__main__":
    import uvicorn
    # Mematikan reload=True karena statreload uvicorn akan memantau folder venv dan menyebabkan [WinError 1450]
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
