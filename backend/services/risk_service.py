import math
import logging
import datetime
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from config import Config
from utils.mt5_utils import check_spread, is_cent_account, is_crypto_symbol

class RiskService:
    """
    Institutional Risk Service:
    - Dynamic Lot Sizing (Dollars, Percent, Cent Account)
    - Circuit Breakers: Adaptive Spread, Max Drawdown, Friday Liquidator
    - News Hard Blackout Filter (Macro Defense Protocol +/- 15 mins)
    - Anti-Hedging (Mutual Exclusion) & Pyramiding Control
    - Volatility Anomaly Detection
    """
    
    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.max_pyramiding = 3
        # Tracking eksekusi Friday Liquidator agar hanya berjalan 1x per hari Sabtu per simbol
        self._liquidated_dates_by_symbol = {}

    def calculate_lot_size(self, symbol: str, sl_distance: float) -> float:
        """
        Kalkulasi ukuran lot adaptif berbasis risiko modal (Fixed Lot / Dollars / Percent / Cent Account).
        Dilengkapi dengan Max Lot Safety Cap (fat-finger protection).
        """
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            logging.error(f"{symbol} not found in MT5.")
            return 0.01

        step = symbol_info.volume_step if symbol_info.volume_step > 0 else 0.01
        min_lot = symbol_info.volume_min if symbol_info.volume_min > 0 else 0.01
        broker_max_lot = symbol_info.volume_max if symbol_info.volume_max > 0 else 100.0
        max_lot_cap = getattr(Config, 'MAX_LOT_CAP', 0.10)
        effective_max = min(broker_max_lot, max_lot_cap)

        mode = getattr(Config, 'RISK_MODE', 'fixed').lower()

        # 1. Mode Fixed Lot (Sangat aman & direkomendasikan untuk retail / micro / cent account)
        if mode == 'fixed':
            fixed_lot = getattr(Config, 'FIXED_LOT_SIZE', 0.01)
            calc_lot = math.floor(fixed_lot / step) * step
            lot = max(min_lot, min(effective_max, round(calc_lot, 2)))
            logging.info(f"[LOT SIZING - FIXED] Symbol: {symbol} | Lot: {lot} (Config Fixed: {fixed_lot}, Cap: {effective_max})")
            return lot

        # 2. Mode Dinamis (Dollars atau Percent)
        account_info = mt5.account_info()
        is_cent = is_cent_account(symbol)
        base_risk_dollars = Config.MAX_RISK_DOLLARS

        if mode == 'percent':
            equity = account_info.equity if account_info and account_info.equity > 0 else (account_info.balance if account_info else 1000.0)
            base_risk_dollars = max(1.0, equity * (getattr(Config, 'MAX_RISK_PERCENT', 1.0) / 100.0))
            logging.info(f"[RISK UI PERCENT] Equity: {equity:.2f} {'USC' if is_cent else '$'} | Risk: {Config.MAX_RISK_PERCENT}% -> Max Risk UI: {base_risk_dollars:.2f}")
        else: # dollars
            if is_cent:
                base_risk_dollars = base_risk_dollars * 100.0
                logging.info(f"[RISK UI DOLLARS - CENT ACCOUNT] Max Risk: ${Config.MAX_RISK_DOLLARS:.2f} -> {base_risk_dollars:.2f} USC")
            else:
                logging.info(f"[RISK UI DOLLARS] Max Risk UI: ${base_risk_dollars:.2f}")

        tick_value = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size
        
        lot = min_lot
        if tick_size > 0 and tick_value > 0 and sl_distance > 0:
            money_per_unit = tick_value / tick_size
            loss_for_one_lot = sl_distance * money_per_unit
            
            if loss_for_one_lot > 0:
                raw_lot = base_risk_dollars / loss_for_one_lot
                calc_lot = math.floor(raw_lot / step) * step
                lot = max(min_lot, min(effective_max, round(calc_lot, 2)))
                est_loss = lot * loss_for_one_lot
                logging.info(f"[LOT SIZING] Risk: {base_risk_dollars:.2f} | Jarak SL: {sl_distance:.2f} | Lot: {lot} (Cap: {effective_max}, Est. Rugi: {est_loss:.2f})")
                
        return lot

    def check_spread_limit(self, symbol: str) -> bool:
        """Pengecekan sekring spread adaptif."""
        spread = check_spread(symbol)
        rates_spread = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 15)
        if rates_spread is not None and len(rates_spread) >= 15:
            df_spread = pd.DataFrame(rates_spread)
            avg_spread = df_spread['spread'].mean()
            dynamic_spread_limit = max(Config.SPREAD_LIMIT_POINTS, int(avg_spread * 2.5))
        else:
            dynamic_spread_limit = Config.SPREAD_LIMIT_POINTS
            
        if spread is not None and spread > dynamic_spread_limit:
            logging.warning(f"[SEKRING] Eksekusi ditolak: Spread {spread} poin melebihi batas adaptif {dynamic_spread_limit}")
            return False
        return True

    def check_drawdown_limit(self) -> bool:
        """Pengecekan batas maksimum drawdown akun."""
        account_info = mt5.account_info()
        if account_info is not None and account_info.balance > 0:
            dd_percent = (account_info.balance - account_info.equity) / account_info.balance
            if dd_percent > (Config.MAX_DRAWDOWN_PERCENT / 100.0):
                logging.warning(f"[SEKRING] Max Drawdown {Config.MAX_DRAWDOWN_PERCENT}% REACHED! Equity: {account_info.equity}")
                self.supervisor.trigger_max_drawdown()
                return False
        return True

    def check_friday_liquidator(self, symbol: str) -> bool:
        """
        Cek apakah hari Sabtu pas jam 00:00 WIB (setelah candle penutupan Jumat).
        Hanya berjalan tepat 1x pas pukul 00:00 WIB untuk pair non-crypto (Forex/Komoditas)
        guna mencegah risiko gap akhir pekan.
        Pasar Crypto (BTCUSD, dsb) yang berjalan 24/7 dikecualikan (tidak ditutup).
        Setelah lewat pukul 00:00 WIB, semua sistem berjalan normal seperti biasa.
        """
        # 1. Pasar Crypto buka 24/7 di akhir pekan tanpa penutupan pasar, dikecualikan
        if is_crypto_symbol(symbol):
            return False

        # 2. Cek waktu aktual dalam zona WIB (UTC+7)
        wib_tz = datetime.timezone(datetime.timedelta(hours=7))
        now_wib = datetime.datetime.now(tz=wib_tz)

        # 3. Hanya aktif tepat di hari Sabtu (weekday == 5) pukul 00:00 WIB (window toleransi 00:00 - 00:04 WIB)
        if now_wib.weekday() == 5 and now_wib.hour == 0 and now_wib.minute < 5:
            date_str = now_wib.strftime("%Y-%m-%d")
            # Pastikan hanya berjalan 1x dalam hari Sabtu tersebut untuk simbol ini
            if date_str in self._liquidated_dates_by_symbol.get(symbol, set()):
                return False

            if symbol not in self._liquidated_dates_by_symbol:
                self._liquidated_dates_by_symbol[symbol] = set()
            self._liquidated_dates_by_symbol[symbol].add(date_str)

            logging.warning(
                f"[SEKRING] Friday Liquidator Active 1x ({symbol}, Sabtu {now_wib.strftime('%H:%M:%S')} WIB)! "
                f"Melikuidasi posisi terbuka non-crypto untuk mengamankan gap akhir pekan."
            )
            self.supervisor.trigger_friday_liquidator()
            return True

        return False

    def check_news_blackout(self) -> tuple[bool, str]:
        """
        P0-2: News Hard Blackout Filter (Institutional Macro Defense Protocol).
        Larang order baru dalam rentang [-15 menit, +15 menit] dari rilis berita High Impact.
        Returns: (is_blackout: bool, reason: str)
        """
        try:
            from database import get_next_high_impact_event
            event = get_next_high_impact_event()
            if not event:
                return False, ""
                
            seconds = event.get("seconds_remaining", 99999)
            blackout_window_sec = Config.NEWS_BLACKOUT_MINUTES * 60
            
            # Jika rentang waktu berada dalam [-blackout_window, +blackout_window]
            if -blackout_window_sec <= seconds <= blackout_window_sec:
                event_name = event.get("event_name", "High Impact News")
                currency = event.get("currency", "USD")
                minutes = round(seconds / 60.0, 1)
                reason = f"News Hard Blackout ({currency}: {event_name}) dalam {minutes} menit (Jendela +/- {Config.NEWS_BLACKOUT_MINUTES}m)"
                return True, reason
        except Exception as e:
            logging.debug(f"[RiskService News Blackout Check] Error: {e}")
        return False, ""

    def validate_execution_allowed(self, symbol: str, action: int, trade_mode: str, prob_runner: float = None) -> bool:
        """
        Validasi menyeluruh sebelum pengiriman order (Mutual exclusion, news blackout, hit-and-run limit, pyramiding).
        """
        # 1. Cek News Hard Blackout (P0-2)
        is_blackout, blackout_reason = self.check_news_blackout()
        if is_blackout:
            logging.warning(f"[NEWS BLACKOUT] ⛔ Order {trade_mode} dibatalkan: {blackout_reason}")
            return False

        # 2. Cek Anti-Hedging (Mutual Exclusion)
        positions = mt5.positions_get(symbol=symbol)
        opposite_action = mt5.ORDER_TYPE_SELL if action == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        opposite_name = "SELL" if action == mt5.ORDER_TYPE_BUY else "BUY"
        action_name = "BUY" if action == mt5.ORDER_TYPE_BUY else "SELL"
        
        if positions:
            opposite_positions = [p for p in positions if p.type == opposite_action]
            if len(opposite_positions) > 0:
                opp_tickets = [f"#{p.ticket} ({p.comment})" for p in opposite_positions]
                logging.warning(
                    f"[MUTUAL EXCLUSION] ⛔ Order {action_name} ({trade_mode}) DITOLAK: "
                    f"Akun memiliki {len(opposite_positions)} posisi berlawanan ({opposite_name}: {', '.join(opp_tickets)})."
                )
                return False

        # 3. Mode HIT_RUN: Maksimal 1 posisi aktif
        if trade_mode == "HIT_RUN" and positions:
            hr_positions = [p for p in positions if "HIT_RUN" in (p.comment or "").upper()]
            if len(hr_positions) >= 1:
                logging.warning(f"[HIT_RUN LIMIT] Order ditolak: Sudah ada 1 posisi Hit & Run aktif (Tiket {hr_positions[0].ticket}).")
                return False

        # 4. Mode RUNNER: Scale-in diperbolehkan HANYA jika posisi sebelumnya sudah running profit
        same_dir_positions = [p for p in positions if p.type == action] if positions else []
        if trade_mode == "RUNNER" and len(same_dir_positions) > 0:
            for p in same_dir_positions:
                if p.profit <= 0:
                    logging.warning(f"[RUNNER PYRAMIDING] Posisi Runner sebelumnya (Tiket {p.ticket}) belum profit (${p.profit:.2f}). Scale-In ditolak.")
                    return False
            logging.info(f"[RUNNER PYRAMIDING] ✅ Semua ({len(same_dir_positions)}) Runner profit. Scale-In diizinkan.")
        elif trade_mode != "RUNNER":
            entry_thresh = getattr(Config, 'AI_NORMAL_ENTRY_THRESHOLD', 75.0) / 100.0
            is_high_prob = prob_runner is not None and prob_runner >= entry_thresh
            if not is_high_prob and len(same_dir_positions) >= self.max_pyramiding:
                logging.warning(f"[PYRAMIDING] Limit dinamis {self.max_pyramiding} tercapai. Order ditolak.")
                return False

        return True
