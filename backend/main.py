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
