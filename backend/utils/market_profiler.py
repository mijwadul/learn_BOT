import logging
import MetaTrader5 as mt5
import numpy as np
from datetime import datetime, timedelta
from utils.mt5_utils import resolve_broker_symbol

logger = logging.getLogger(__name__)

# Cache in-memory hasil profiling otomatis per pair (refresh tiap 30 menit)
_AUTONOMOUS_TF_CACHE = {}

# Tangga Fraktal Multi-Timeframe Berkelanjutan (BBMA Oma Ally Compliant)
FRACTAL_LADDER = [
    # (Entry TF, MT5 Constant, Setup TF, Trend TF)
    ("M1",  mt5.TIMEFRAME_M1,  "M5",  "M15"),
    ("M5",  mt5.TIMEFRAME_M5,  "M15", "H1"),
    ("M15", mt5.TIMEFRAME_M15, "H1",  "H4"),
    ("M30", mt5.TIMEFRAME_M30, "H4",  "D1"),
    ("H1",  mt5.TIMEFRAME_H1,  "H4",  "D1"),
]

def resolve_autonomous_timeframe_hierarchy(symbol: str, max_friction_ratio: float = 0.20) -> dict:
    """
    Autonomous Pair Profiler (Zero Hardcoding):
    Secara mandiri menentukan hierarki timeframe (Entry, Setup, Trend) untuk APAPUN simbol yang diberikan
    (misal: XAUUSD, XAGUSD, BTCUSD, US30, EURUSD, GBPJPY, dsb) tanpa perlu campur tangan manusia.
    
    Metodologi Otonom:
    1. Memindai mikrostruktur broker MT5 (Spread & Candle Range) pada tangga fraktal.
    2. Menghitung Friction Ratio = (Spread Points * Point) / ATR(14).
    3. Memilih timeframe terendah yang memiliki nilai Friction <= max_friction_ratio.
       - Jika pair likuid (seperti Gold) memenuhi syarat di M1 -> Entry M1, Setup M5, Trend M15.
       - Jika pair seperti XAGUSD atau Kripto tertentu baru efisien di M5 -> Entry M5, Setup M15, Trend H1.
       - Jika spread forex/eksotik lebih lebar -> Entry M15, Setup H1, Trend H4.
    """
    clean_sym = (symbol or "XAUUSD").upper().strip()
    
    # Cek cache
    now = datetime.now()
    if clean_sym in _AUTONOMOUS_TF_CACHE:
        cached = _AUTONOMOUS_TF_CACHE[clean_sym]
        if cached.get("expires_at", now) > now:
            return cached["profile"]
            
    broker_sym = resolve_broker_symbol(clean_sym)
    sym_info = mt5.symbol_info(broker_sym) if broker_sym else None
    
    if sym_info is None:
        # Fallback aman jika broker offline / mock testing
        fallback = {
            "entry_tf": "M5",
            "setup_tf": "M15",
            "trend_tf": "H1",
            "friction_ratio": 0.10,
            "auto_discovered": False,
            "symbol": clean_sym,
            "broker_symbol": broker_sym or clean_sym
        }
        return fallback

    point = sym_info.point if sym_info.point else 0.0001
    spread_pts = sym_info.spread if sym_info.spread else 20
    spread_cost = spread_pts * point
    
    selected_ladder = None
    selected_friction = 1.0

    for entry_tf, tf_const, setup_tf, trend_tf in FRACTAL_LADDER:
        try:
            rates = mt5.copy_rates_from_pos(broker_sym, tf_const, 0, 20)
            if rates is not None and len(rates) >= 10:
                highs = rates['high']
                lows = rates['low']
                ranges = highs - lows
                avg_range = float(np.mean(ranges[-14:])) if len(ranges) >= 14 else float(np.mean(ranges))
                
                if avg_range > 0:
                    friction = spread_cost / avg_range
                    if friction <= max_friction_ratio:
                        selected_ladder = (entry_tf, setup_tf, trend_tf)
                        selected_friction = friction
                        break
                    else:
                        if friction < selected_friction:
                            selected_friction = friction
                            selected_ladder = (entry_tf, setup_tf, trend_tf)
        except Exception as e:
            logger.debug(f"[PROFILER] Gagal cek {broker_sym} di {entry_tf}: {e}")

    if selected_ladder is None:
        selected_ladder = ("M15", "H1", "H4")

    profile = {
        "entry_tf": selected_ladder[0],
        "setup_tf": selected_ladder[1],
        "trend_tf": selected_ladder[2],
        "friction_ratio": round(float(selected_friction), 4),
        "auto_discovered": True,
        "symbol": clean_sym,
        "broker_symbol": broker_sym
    }

    logger.info(
        f"[AUTONOMOUS PROFILER] 🌐 {clean_sym} [{broker_sym}] profil otomatis terbentuk: "
        f"Entry {profile['entry_tf']} | Setup {profile['setup_tf']} | Trend {profile['trend_tf']} "
        f"(Spread: {spread_pts} pts, Friction: {profile['friction_ratio']*100:.1f}%)"
    )

    _AUTONOMOUS_TF_CACHE[clean_sym] = {
        "profile": profile,
        "expires_at": now + timedelta(minutes=30)
    }

    return profile
