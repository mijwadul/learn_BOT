import os
from dotenv import load_dotenv

load_dotenv()

try:
    from utils.settings_manager import settings_manager
except ImportError:
    from backend.utils.settings_manager import settings_manager

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
    MAGIC_NUMBER_UNIFIED = int(os.getenv("MAGIC_NUMBER_UNIFIED", "234003"))
    MAGIC_NUMBER = MAGIC_NUMBER_BASE # Backward compatibility
    
    # Institutional Risk & Execution Protocols
    NEWS_BLACKOUT_MINUTES = int(os.getenv("NEWS_BLACKOUT_MINUTES", "15")) # Hard blackout T-15m to T+15m
    REQUOTE_MAX_RETRIES = int(os.getenv("REQUOTE_MAX_RETRIES", "2")) # Smart requote retry count
    DYNAMIC_SLIPPAGE_MULTIPLIER = float(os.getenv("DYNAMIC_SLIPPAGE_MULTIPLIER", "1.5")) # Spread multiplier for deviation
    
    RISK_MODE = str(settings_manager.get_setting("risk_mode", os.getenv("RISK_MODE", "fixed"))).lower()
    FIXED_LOT_SIZE = float(settings_manager.get_setting("fixed_lot_size", os.getenv("FIXED_LOT_SIZE", "0.01")))
    MAX_RISK_DOLLARS = float(settings_manager.get_setting("max_risk_dollars", os.getenv("MAX_RISK_DOLLARS", "10.0")))
    MAX_RISK_PERCENT = float(settings_manager.get_setting("max_risk_percent", os.getenv("MAX_RISK_PERCENT", "1.0")))
    MAX_LOT_CAP = float(settings_manager.get_setting("max_lot_cap", os.getenv("MAX_LOT_CAP", "0.10")))
    MAX_DRAWDOWN_PERCENT = 30.0 # Max drawdown reset JIKA menyentuh 30% dari ekuitas
    SPREAD_LIMIT_POINTS = 400 # Blokir eksekusi jika spread > 400 poin
    AI_NORMAL_ENTRY_THRESHOLD = float(settings_manager.get_setting("ai_normal_entry_threshold", os.getenv("AI_NORMAL_ENTRY_THRESHOLD", "60.0")))
    AI_RUNNER_ENTRY_THRESHOLD = float(settings_manager.get_setting("ai_runner_entry_threshold", os.getenv("AI_RUNNER_ENTRY_THRESHOLD", "55.0")))

    @classmethod
    def reload_settings(cls):
        """Reload all runtime risk and AI threshold settings from SettingsManager."""
        cls.RISK_MODE = str(settings_manager.get_setting("risk_mode", "fixed")).lower()
        cls.FIXED_LOT_SIZE = float(settings_manager.get_setting("fixed_lot_size", 0.01))
        cls.MAX_RISK_DOLLARS = float(settings_manager.get_setting("max_risk_dollars", 10.0))
        cls.MAX_RISK_PERCENT = float(settings_manager.get_setting("max_risk_percent", 1.0))
        cls.MAX_LOT_CAP = float(settings_manager.get_setting("max_lot_cap", 0.10))
        cls.AI_NORMAL_ENTRY_THRESHOLD = float(settings_manager.get_setting("ai_normal_entry_threshold", 60.0))
        cls.AI_RUNNER_ENTRY_THRESHOLD = float(settings_manager.get_setting("ai_runner_entry_threshold", 55.0))

    @classmethod
    def get_ai_threshold(cls, symbol: str = None, mode: str = "normal") -> float:
        """Get AI entry threshold with support for per-pair override."""
        return settings_manager.get_ai_threshold(symbol=symbol, mode=mode)

    # AI Intelligence: Online Learning & Market Regime (ADX)
    ENABLE_ONLINE_LEARNING = os.getenv("ENABLE_ONLINE_LEARNING", "true").lower() == "true"
    ONLINE_LEARNING_INTERVAL_DAYS = int(os.getenv("ONLINE_LEARNING_INTERVAL_DAYS", "7")) # Jadwal bergantian per minggu (7 hari)
    ADX_TREND_THRESHOLD = float(os.getenv("ADX_TREND_THRESHOLD", "25.0")) # Di atas ini: Rezim Trending Kuat (Prioritas Runner)
    ADX_RANGING_THRESHOLD = float(os.getenv("ADX_RANGING_THRESHOLD", "20.0")) # Di bawah ini: Rezim Choppy/Sideways (Blokir Runner, Utamakan Scalp Hit&Run)

    # Friction Guard: Batas maksimal rasio Spread terhadap ATR (20% default)
    MAX_SPREAD_TO_ATR_RATIO = float(os.getenv("MAX_SPREAD_TO_ATR_RATIO", "0.20"))
    DEFAULT_TIMEFRAME_PROFILE = {"entry_tf": "M5", "setup_tf": "M15", "trend_tf": "H1"}

    @classmethod
    def get_timeframe_profile(cls, symbol: str) -> dict:
        """
        Autonomous Multi-Timeframe Discovery (Zero Hardcoding):
        Secara otonom memindai dan menentukan hierarki timeframe terbaik untuk APAPUN pair/simbol
        berdasarkan rasio spread dan volatilitas (ATR) riil dari broker.
        """
        try:
            from utils.market_profiler import resolve_autonomous_timeframe_hierarchy
            return resolve_autonomous_timeframe_hierarchy(symbol, max_friction_ratio=cls.MAX_SPREAD_TO_ATR_RATIO)
        except Exception:
            return cls.DEFAULT_TIMEFRAME_PROFILE

