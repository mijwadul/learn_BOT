import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # MT5 Configurations
    MT5_SERVER = os.getenv("MT5_SERVER", "Demo Server") # Ubah sesuai broker
    MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
    MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
    MT5_PATH = os.getenv("MT5_PATH", "") # Path opsional ke terminal64.exe
    
    # PostgreSQL Configuration
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "bbma_trading")
    
    # SQLAlchemy URL
    DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    SYNC_DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    # Trading Configurations
    MACRO_JSON_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json" # Akan segera ditinggalkan
    SYMBOL = os.getenv("SYMBOL", "AUTO") # "AUTO" untuk deteksi cerdas (XAUUSD, XAUUSDm, XAUUSDc), atau nama spesifik
    # Magic Number Standardization (Institutional Standards)
    MAGIC_NUMBER_BASE = int(os.getenv("MAGIC_NUMBER_BASE", "234000"))
    MAGIC_NUMBER_NORMAL = int(os.getenv("MAGIC_NUMBER_NORMAL", "234001"))
    MAGIC_NUMBER_RUNNER = int(os.getenv("MAGIC_NUMBER_RUNNER", "234002"))
    MAGIC_NUMBER = MAGIC_NUMBER_BASE # Backward compatibility
    
    # Institutional Risk & Execution Protocols
    NEWS_BLACKOUT_MINUTES = int(os.getenv("NEWS_BLACKOUT_MINUTES", "15")) # Hard blackout T-15m to T+15m
    REQUOTE_MAX_RETRIES = int(os.getenv("REQUOTE_MAX_RETRIES", "2")) # Smart requote retry count
    DYNAMIC_SLIPPAGE_MULTIPLIER = float(os.getenv("DYNAMIC_SLIPPAGE_MULTIPLIER", "1.5")) # Spread multiplier for deviation
    
    RISK_MODE = os.getenv("RISK_MODE", "dollars") # Mode resiko: "dollars" ($ tetap) atau "percent" (% modal)
    MAX_RISK_DOLLARS = float(os.getenv("MAX_RISK_DOLLARS", "10.0")) # Toleransi batas rugi per transaksi ($)
    MAX_RISK_PERCENT = float(os.getenv("MAX_RISK_PERCENT", "1.0")) # Toleransi batas rugi per transaksi (% modal)
    MAX_DRAWDOWN_PERCENT = 30.0 # Max drawdown reset JIKA menyentuh 30% dari ekuitas
    SPREAD_LIMIT_POINTS = 400 # Blokir eksekusi jika spread > 400 poin
    AI_NORMAL_ENTRY_THRESHOLD = 75.0 # Batas minimal probabilitas AI untuk mengizinkan OP baru (%)

    # AI Intelligence: Online Learning & Market Regime (ADX)
    ENABLE_ONLINE_LEARNING = os.getenv("ENABLE_ONLINE_LEARNING", "true").lower() == "true"
    ADX_TREND_THRESHOLD = float(os.getenv("ADX_TREND_THRESHOLD", "25.0")) # Di atas ini: Rezim Trending Kuat (Prioritas Runner)
    ADX_RANGING_THRESHOLD = float(os.getenv("ADX_RANGING_THRESHOLD", "20.0")) # Di bawah ini: Rezim Choppy/Sideways (Blokir Runner, Utamakan Scalp Hit&Run)
