from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd


class BaseProfile:
    """
    Abstract Base Class untuk profil kuantitatif per instrumen/pair.
    Mengisolasi parameter risiko, geometri RR, dan kaedah teknikal khusus aset.
    """
    symbol: str = "DEFAULT"
    
    # 1. Geometri Risk to Reward & Zone Buffers
    rr_normal: float = 2.0           # Target RR Mode Normal (Scalp 1:2.0)
    rr_runner: float = 3.5           # Target RR Mode Runner (Trend 1:3.5)
    sl_atr_mult: float = 1.2         # Jarak SL berbasis ATR (1.2 * ATR)
    zone_buffer_ratio: float = 0.25  # Buffer toleransi batas zona LWMA (* ATR)
    
    # 2. Kaedah & Filter Re-entry
    mandate_zzl: bool = True         # Wajib Zon Zero Loss (ZZL) hierarki EMA 50
    breakeven_r: float = 1.0         # Excursion R untuk memindahkan SL ke Break-Even
    min_cooldown_bars: int = 18      # Jeda bar minimum antar sinyal (~90 menit di M5)
    
    # 3. Kriteria Kelulusan OOS (Fit & Proper Thresholds)
    oos_criteria_normal: Dict[str, float] = {
        "min_win_rate": 40.0,        # Pada RR 1:2.0, Win Rate 40% menghasilkan PF 1.33 (Lolos!)
        "min_profit_factor": 1.30,
        "min_sharpe_ratio": 0.80,
        "max_drawdown": 20.0,
        "min_trades": 25
    }
    
    oos_criteria_runner: Dict[str, float] = {
        "min_win_rate": 28.0,        # Pada RR 1:3.5+, Win Rate 28% menghasilkan PF 1.36 (Lolos!)
        "min_profit_factor": 1.20,
        "min_sharpe_ratio": 0.50,
        "max_drawdown": 35.0,
        "min_trades": 20
    }

    @classmethod
    def get_criteria(cls, mode: str) -> Dict[str, float]:
        """Mengembalikan kriteria kelulusan OOS sesuai mode."""
        m = str(mode or "normal").lower()
        if m == "runner":
            return cls.oos_criteria_runner.copy()
        return cls.oos_criteria_normal.copy()

    @classmethod
    def filter_zzl(cls, df: pd.DataFrame, buy_mask: np.ndarray, sell_mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Menerapkan filter Zon Zero Loss (ZZL) murni:
        - Buy: Candlestick close >= EMA 50 & Mid BB (SMA 20) >= EMA 50
        - Sell: Candlestick close <= EMA 50 & Mid BB (SMA 20) <= EMA 50
        """
        if not cls.mandate_zzl:
            return buy_mask, sell_mask

        n = len(df)
        if n == 0:
            return buy_mask, sell_mask

        close_vals = df['close'].values
        ema50_vals = df['EMA_50'].values if 'EMA_50' in df.columns else close_vals
        sma20_vals = df['SMA_20'].values if 'SMA_20' in df.columns else close_vals

        zzl_buy = (close_vals >= ema50_vals) & (sma20_vals >= ema50_vals)
        zzl_sell = (close_vals <= ema50_vals) & (sma20_vals <= ema50_vals)

        return (buy_mask & zzl_buy), (sell_mask & zzl_sell)
