from typing import Dict
from .base_profile import BaseProfile


class XAUUSDProfile(BaseProfile):
    """
    Profil Kuantitatif Khusus Emas (XAUUSD / GOLD).
    
    Karakteristik Aset:
    - Fat-tailed, leptokurtic distribution dengan momentum pergerakan impulsif yang kuat.
    - Sangat patuh pada kaedah Zon Zero Loss (ZZL) dan penolakan (rejection) di MA 5/10 LWMA.
    - Memiliki rentang ayunan yang lebar di timeframe M5, sehingga membutuhkan rasio Risk:Reward minimal 1:2.0
      agar ekspektasi matematika positif dan lolos batas kelulusan institusional.
    """
    symbol: str = "XAUUSD"
    
    # 1. Geometri Risk to Reward Khusus Emas
    rr_normal: float = 2.0           # Normal Mode: TP 2.0R vs SL 1.0R (1.2 ATR)
    rr_runner: float = 3.5           # Runner Mode: TP 3.5R vs SL 1.0R (1.2 ATR)
    sl_atr_mult: float = 1.2         # Jarak SL optimal untuk menyerap volatilitas mikro M5
    zone_buffer_ratio: float = 0.25  # Buffer batas LWMA khusus volatilitas Gold
    
    # 2. Kaedah & Filter Re-entry
    mandate_zzl: bool = True         # Wajib Zon Zero Loss murni (eliminasi counter-trend noise)
    breakeven_r: float = 1.0         # Geser ke BE setelah floating profit mencapai +1.0R
    min_cooldown_bars: int = 18      # Jeda 18 bar (~90 menit di M5) untuk mencegah over-trading
    
    # 3. Kriteria Kelulusan OOS (Fit & Proper Test Khusus XAUUSD)
    oos_criteria_normal: Dict[str, float] = {
        "min_win_rate": 40.0,        # Pada RR 1:2.0, Win Rate 40% menghasilkan PF 1.33 (Lolos!)
        "min_profit_factor": 1.30,
        "min_sharpe_ratio": 0.80,
        "max_drawdown": 20.0,
        "min_trades": 25
    }
    
    oos_criteria_runner: Dict[str, float] = {
        "min_win_rate": 28.0,        # Pada RR 1:3.5, Win Rate 28% menghasilkan PF 1.36 (Lolos!)
        "min_profit_factor": 1.20,
        "min_sharpe_ratio": 0.50,
        "max_drawdown": 35.0,
        "min_trades": 20
    }
