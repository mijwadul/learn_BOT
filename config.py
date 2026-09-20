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
    SYMBOL = "XAUUSDm" # Contoh symbol default
    MAGIC_NUMBER = 123456
    MAX_RISK_DOLLARS = 10.0 # Toleransi batas rugi per transaksi ($)
    MAX_DRAWDOWN_PERCENT = 30.0 # Max drawdown reset JIKA menyentuh 30% dari ekuitas
    SPREAD_LIMIT_POINTS = 400 # Blokir eksekusi jika spread > 400 poin
