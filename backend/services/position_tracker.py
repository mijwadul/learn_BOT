import logging
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from config import Config
from .order_router import OrderRouter

class PositionTracker:
    """
    Position Tracker & Lifecycle Manager:
    - Active Position Monitoring & Multi-Layer Mode Detection (Magic/Cache/DB/Comment)
    - Break-Even Milestones (RR 1:1 for Normal, RR 1:2 for Runner)
    - Milestone Scaling: Partial Close 50% & Maximum Learned RR Exit
    - AI Reversal & Exhaustion Exit Detection
    - P0-2: Pre-News Profit Guard (Auto Shift SL to BE before High Impact News)
    - P2-3: Startup Position Reconciliation (Orphan Trade Guard: Auto-attach Emergency SL)
    """

    def __init__(self, order_router: OrderRouter, researcher=None):
        self.order_router = order_router
        self.researcher = researcher
        self.position_modes = {}

    def detect_position_mode(self, pos) -> str:
        """
        Deteksi Mode Posisi yang Tangguh (Multi-Layer: Magic Number -> Cache -> Database -> Comment)
        """
        magic = getattr(pos, 'magic', 0)
        if magic == Config.MAGIC_NUMBER_RUNNER:
            return "RUNNER"
        if magic == Config.MAGIC_NUMBER_NORMAL:
            return "NORMAL"
            
        ticket = pos.ticket
        if ticket in self.position_modes:
            return self.position_modes[ticket]
            
        comment = (pos.comment or "").upper()
        if "RUNNER" in comment:
            self.position_modes[ticket] = "RUNNER"
            return "RUNNER"
        if "HIT_RUN" in comment:
            self.position_modes[ticket] = "NORMAL"
            return "NORMAL"
            
        try:
            from database import Session, sync_engine, TradeLog
            with Session(sync_engine) as session:
                t_rec = session.query(TradeLog).filter(TradeLog.ticket == ticket).first()
                if t_rec and t_rec.mode:
                    mode = "RUNNER" if "RUNNER" in t_rec.mode.upper() else "NORMAL"
                    self.position_modes[ticket] = mode
                    return mode
        except Exception:
            pass
            
        return "NORMAL"

    def reconcile_positions_on_startup(self, symbol: str):
        """
        P2-3: Startup Position Reconciliation (Audit & Orphan Trade Defense).
        Audit seluruh posisi terbuka di broker:
        - Jika terdeteksi posisi tanpa SL (sl == 0), pasang emergency Hard SL instan (5.0 / 500 pts).
        """
        try:
            positions = mt5.positions_get(symbol=symbol)
            if not positions:
                logging.info("[RECONCILIATION] ✅ Tidak ada posisi floating saat startup.")
                return
                
            logging.info(f"[RECONCILIATION] Menjalankan audit untuk {len(positions)} posisi floating...")
            for pos in positions:
                mode = self.detect_position_mode(pos)
                self.position_modes[pos.ticket] = mode
                
                # Cek apakah posisi tidak memiliki Hard SL
                if pos.sl == 0.0 or pos.sl is None:
                    logging.warning(
                        f"[ORPHAN TRADE GUARD] ⚠️ Posisi #{pos.ticket} ({mode}) tidak memiliki Stop Loss! "
                        f"Memasang Emergency Hard SL..."
                    )
                    emergency_distance = 5.0 # Jarak darurat 500 poin (misal Gold $5.00)
                    new_sl = round(pos.price_open - emergency_distance, 2) if pos.type == mt5.ORDER_TYPE_BUY else round(pos.price_open + emergency_distance, 2)
                    
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": symbol,
                        "sl": float(new_sl),
                        "tp": float(pos.tp),
                    }
                    res = mt5.order_send(req)
                    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                        logging.info(f"[ORPHAN TRADE GUARD] ✅ Emergency SL berhasil dipasang pada {new_sl} untuk tiket #{pos.ticket}.")
                    else:
                        logging.error(f"[ORPHAN TRADE GUARD] ❌ Gagal memasang emergency SL: {res.retcode if res else 'None'}")
                else:
                    logging.info(f"[RECONCILIATION] Posisi #{pos.ticket} valid: Mode={mode} | SL={pos.sl} | TP={pos.tp}")
        except Exception as e:
            logging.error(f"[RECONCILIATION] Gagal rekonsiliasi posisi: {e}")

    def protect_positions_before_news(self, symbol: str):
        """
        P0-2: Otomatis geser Stop Loss ke Break Even (BE) jika ada posisi aktif yang sedang profit
        menjelang rilis berita High Impact (< 15 menit).
        """
        try:
            from database import get_next_high_impact_event
            event = get_next_high_impact_event()
            if not event:
                return
                
            seconds = event.get("seconds_remaining", 99999)
            # Jika berita akan rilis dalam 0-15 menit ke depan
            if 0 <= seconds <= (Config.NEWS_BLACKOUT_MINUTES * 60):
                positions = mt5.positions_get(symbol=symbol)
                if positions:
                    for pos in positions:
                        if pos.profit > 0 and abs(pos.sl - pos.price_open) > 0.10:
                            logging.warning(
                                f"[PRE-NEWS PROTECT] 🛡️ Menjelang berita {event.get('event_name')} ({round(seconds/60.1, 1)}m), "
                                f"menggeser SL posisi #{pos.ticket} (Profit: ${pos.profit:.2f}) ke Break-Even!"
                            )
                            self.order_router.modify_sl_to_break_even(pos.ticket, symbol)
        except Exception as e:
            logging.debug(f"[Pre-News Protect] {e}")

    def process_active_positions(self, symbol: str, latest_df=None, latest_probs=None):
        """
        Loop evaluasi manajemen trade aktif:
        - HIT_RUN: Target 1:1 -> SL ke BE, Target 1:2 -> Full Close
        - RUNNER: Milestone 1:2 -> Partial Close 50% & SL ke BE, Max RR / Reversal -> Full Close
        """
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            return

        # Cek proteksi berita
        self.protect_positions_before_news(symbol)

        for pos in positions:
            ticket = pos.ticket
            entry_price = pos.price_open
            current_price = pos.price_current
            sl_price = pos.sl
            
            if pos.type == mt5.ORDER_TYPE_BUY:
                initial_risk = abs(entry_price - sl_price) if sl_price > 0 else 0
                current_gain = current_price - entry_price
            else:
                initial_risk = abs(sl_price - entry_price) if sl_price > 0 else 0
                current_gain = entry_price - current_price
                
            mode = self.detect_position_mode(pos)
            is_runner = (mode == "RUNNER")
            
            if not is_runner:
                # --- HIT_RUN LOGIC (RR 1:2 Target) ---
                if initial_risk > 0:
                    if current_gain >= (1.0 * initial_risk) and abs(pos.sl - pos.price_open) > 0.05:
                        logging.info(f"[HIT_RUN] Target RR 1:1 tercapai untuk tiket {ticket}. Geser SL ke BE.")
                        self.order_router.modify_sl_to_break_even(ticket, symbol)
                    if current_gain >= (2.0 * initial_risk):
                        logging.info(f"[HIT_RUN] Target RR 1:2 pas tercapai untuk tiket {ticket}. Menjalankan Full Close.")
                        self.order_router.execute_full_close(ticket, reason="Hit & Run: Target RR 1:2 Pas Tercapai (Full Close)", symbol=symbol)
            else:
                # --- RUNNER LOGIC ---
                # 1. Partial close 50% & BE at 2R
                if initial_risk > 0 and current_gain >= (2.0 * initial_risk):
                    if abs(pos.sl - pos.price_open) > 0.05:
                        logging.info(f"[RUNNER] Milestone RR 1:2 tercapai untuk tiket {ticket}. Partial Close 50% & SL ke BE.")
                        self.order_router.execute_partial_close_50(ticket, symbol)
                        self.order_router.modify_sl_to_break_even(ticket, symbol)

                # 2. Maximum learned RR
                max_runner_rr = getattr(self.researcher, 'max_runner_rr', 5.0) if self.researcher else 5.0
                if initial_risk > 0 and current_gain >= (max_runner_rr * initial_risk):
                    logging.info(f"[RUNNER EXIT] 🎯 Maximum RR ({max_runner_rr:.1f}R) tercapai untuk tiket {ticket}. Menjalankan Full Close.")
                    self.order_router.execute_full_close(ticket, reason=f"Runner Exit: Maximum RR ({max_runner_rr:.1f}R) Tercapai", symbol=symbol)
                    continue

                # 3. Reversal Exit Analysis (dengan ADX confirmation filter)
                reversal_detected = False
                reversal_reason = ""
                probs = latest_probs or {}
                p_sell_rev = max(probs.get("runner_sell", 0.0), probs.get("normal_sell", 0.0))
                p_buy_rev = max(probs.get("runner_buy", 0.0), probs.get("normal_buy", 0.0))

                adx_current = 25.0
                if latest_df is not None and not latest_df.empty:
                    if 'adx' in latest_df.columns:
                        val = latest_df['adx'].iloc[-1]
                        if not np.isnan(val):
                            adx_current = float(val)

                if pos.type == mt5.ORDER_TYPE_BUY:
                    if p_sell_rev >= 0.65 and adx_current < 25.0:
                        reversal_detected = True
                        reversal_reason = f"AI mendeteksi lonjakan probabilitas SELL ({p_sell_rev:.2f}) + ADX lemah ({adx_current:.1f} < 25)"
                    elif latest_df is not None and not latest_df.empty and 'EMA_50' in latest_df.columns and 'LWMA_10_Low' in latest_df.columns:
                        c_close = latest_df['close'].iloc[-1]
                        c_ema = latest_df['EMA_50'].iloc[-1]
                        c_lwma = latest_df['LWMA_10_Low'].iloc[-1]
                        if c_close < c_ema and c_close < c_lwma and adx_current < 30.0:
                            reversal_detected = True
                            reversal_reason = f"Reversal Teknis: Close ({c_close:.2f}) menembus bawah EMA 50 ({c_ema:.2f}) & LWMA 10 Low ({c_lwma:.2f}) [ADX: {adx_current:.1f} < 30]"
                elif pos.type == mt5.ORDER_TYPE_SELL:
                    if p_buy_rev >= 0.65 and adx_current < 25.0:
                        reversal_detected = True
                        reversal_reason = f"AI mendeteksi lonjakan probabilitas BUY ({p_buy_rev:.2f}) + ADX lemah ({adx_current:.1f} < 25)"
                    elif latest_df is not None and not latest_df.empty and 'EMA_50' in latest_df.columns and 'LWMA_10_High' in latest_df.columns:
                        c_close = latest_df['close'].iloc[-1]
                        c_ema = latest_df['EMA_50'].iloc[-1]
                        c_lwma = latest_df['LWMA_10_High'].iloc[-1]
                        if c_close > c_ema and c_close > c_lwma and adx_current < 30.0:
                            reversal_detected = True
                            reversal_reason = f"Reversal Teknis: Close ({c_close:.2f}) menembus atas EMA 50 ({c_ema:.2f}) & LWMA 10 High ({c_lwma:.2f}) [ADX: {adx_current:.1f} < 30]"

                if reversal_detected:
                    logging.warning(f"[RUNNER REVERSAL EXIT] ⚠️ Sinyal Reversal terdeteksi untuk tiket {ticket}: {reversal_reason}. Menjalankan Full Close.")
                    self.order_router.execute_full_close(ticket, reason=f"Runner Reversal Exit: {reversal_reason}", symbol=symbol)
