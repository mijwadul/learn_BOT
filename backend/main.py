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
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

@asynccontextmanager
async def lifespan(app: FastAPI):
    dependencies.main_loop = asyncio.get_running_loop()
    try:
        from database import init_db, reset_ai_trade_history
        await init_db()
        logging.info("✅ [STARTUP] Database initialized & schema migrations completed.")

        # Drop file .pkl lama dan bersihkan tabel hard_negatives untuk Fresh Quantitative Baseline
        import os
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parent
        for f in [
            Path("models/model_normal.pkl"),
            Path("models/model_runner.pkl"),
            backend_dir / "models" / "model_normal.pkl",
            backend_dir / "models" / "model_runner.pkl",
        ]:
            if f.exists():
                try:
                    f.unlink()
                    logging.info(f"🗑️ [CLEANUP] Berhasil menghapus model lama: {f}")
                except Exception as e_rm:
                    logging.warning(f"Tidak dapat menghapus {f}: {e_rm}")

        try:
            reset_ai_trade_history(categories=["hard_negatives"])
            logging.info("🗑️ [CLEANUP] Tabel hard_negatives berhasil dikosongkan.")
        except Exception as e_t:
            logging.warning(f"Gagal membersihkan hard_negatives: {e_t}")

    except Exception as e:
        logging.warning(f"⚠️ [STARTUP] DB initialization/cleanup deferred: {e}")
    yield

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

if __name__ == "__main__":
    import uvicorn
    # Mematikan reload=True karena statreload uvicorn akan memantau folder venv dan menyebabkan [WinError 1450]
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
