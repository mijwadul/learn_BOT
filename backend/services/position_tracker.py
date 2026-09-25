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
        self.initial_risks = {}

    def register_position(self, ticket: int, mode: str, sl_distance: float = 0.0):
        """Mendaftarkan posisi aktif baru secara instan saat eksekusi live."""
        self.position_modes[ticket] = mode.upper()
        if sl_distance and sl_distance > 0.1:
            self.initial_risks[ticket] = float(sl_distance)

    def get_or_recover_initial_risk(self, pos, is_runner: bool) -> float:
        """
        Multi-Tier Institutional Recovery untuk Initial Risk (SSOT):
        1. In-memory cache
        2. Database TradeLog (SL asli saat eksekusi)
        3. Database LiveDecisionSample (SL asli saat sinyal)
        4. MT5 History Orders/Deals
        5. Kalkulasi rasio TP awal (TP distance / 2.0 untuk HIT_RUN atau runner_rr untuk RUNNER)
        6. Posisi SL saat ini (jika belum BE)
        7. Fallback aman institusional (5.0 / 500 pts)
        """
        ticket = pos.ticket
        if ticket in self.initial_risks and self.initial_risks[ticket] > 0.5:
            return self.initial_risks[ticket]
            
        entry_price = pos.price_open
        
        # 1. Coba recover dari database TradeLog
        try:
            from database import Session, sync_engine, TradeLog
            with Session(sync_engine) as session:
                t_rec = session.query(TradeLog).filter(TradeLog.ticket == ticket).first()
                if t_rec and t_rec.sl and t_rec.sl > 0:
                    dist = round(abs(entry_price - t_rec.sl), 2)
                    if dist > 0.5:
                        self.initial_risks[ticket] = dist
                        return dist
        except Exception:
            pass

        # 2. Coba recover dari database LiveDecisionSample
        try:
            from database import Session, sync_engine, LiveDecisionSample
            with Session(sync_engine) as session:
                sample = session.query(LiveDecisionSample).filter(LiveDecisionSample.ticket == ticket).first()
                if sample and sample.sl and sample.sl > 0:
                    dist = round(abs(entry_price - sample.sl), 2)
                    if dist > 0.5:
                        self.initial_risks[ticket] = dist
                        return dist
        except Exception:
            pass

        # 3. Coba recover dari MT5 order history
        try:
            history_orders = mt5.history_orders_get(position=ticket)
            if history_orders:
                for h_ord in history_orders:
                    if h_ord.sl > 0:
                        dist = round(abs(entry_price - h_ord.sl), 2)
                        if dist > 0.5:
                            self.initial_risks[ticket] = dist
                            return dist
        except Exception:
            pass

        # 4. Coba kalkulasi dari Hard TP awal
        if pos.tp > 0:
            tp_dist = abs(pos.tp - entry_price)
            if tp_dist > 1.0:
                expected_rr = 4.0 if is_runner else 2.0
                inferred_risk = round(tp_dist / expected_rr, 2)
                if inferred_risk > 0.5:
                    self.initial_risks[ticket] = inferred_risk
                    return inferred_risk

        # 5. Cek apakah SL saat ini belum di BE (masih SL asli)
        if pos.sl > 0:
            current_sl_dist = round(abs(entry_price - pos.sl), 2)
            if current_sl_dist > 1.0:
                is_be = (pos.type == mt5.ORDER_TYPE_BUY and pos.sl >= entry_price) or \
                        (pos.type == mt5.ORDER_TYPE_SELL and pos.sl <= entry_price)
                if not is_be:
                    self.initial_risks[ticket] = current_sl_dist
                    return current_sl_dist

        # 6. Fallback aman institusional (Gold $5.00)
        fallback_risk = 5.0
        self.initial_risks[ticket] = fallback_risk
        return fallback_risk

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
                is_runner = (mode == "RUNNER")
                self.get_or_recover_initial_risk(pos, is_runner)
                
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
        Loop evaluasi manajemen trade aktif institusional:
        - Pemulihan & pelacakan initial risk yang persisten (anti-hilang saat SL geser ke BE)
        - Evaluasi Thesis Invalidation & Reversal Exit untuk SEMUA posisi (NORMAL & RUNNER)
        - HIT_RUN: Target 1:1 -> SL ke BE, Target 1:2 -> Full Close
        - RUNNER: Milestone 1:2 -> Partial Close 50% & SL ke BE, Max RR Exit -> Full Close
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
            
            mode = self.detect_position_mode(pos)
            is_runner = (mode == "RUNNER")
            initial_risk = self.get_or_recover_initial_risk(pos, is_runner)
            
            # Cek apakah posisi sudah berada di Break-Even
            is_already_be = (pos.type == mt5.ORDER_TYPE_BUY and pos.sl >= entry_price) or \
                            (pos.type == mt5.ORDER_TYPE_SELL and 0 < pos.sl <= entry_price)

            if pos.type == mt5.ORDER_TYPE_BUY:
                current_gain = current_price - entry_price
            else:
                current_gain = entry_price - current_price

            current_r = round(current_gain / initial_risk, 2) if initial_risk > 0 else 0.0

            # =========================================================================
            # 1. EVALUASI REVERSAL & THESIS INVALIDATION (Berlaku untuk SEMUA mode)
            # =========================================================================
            reversal_detected = False
            reversal_reason = ""
            probs = latest_probs or {}
            p_sell_rev = max(probs.get("runner_sell", 0.0), probs.get("normal_sell", 0.0))
            p_buy_rev = max(probs.get("runner_buy", 0.0), probs.get("normal_buy", 0.0))

            if latest_df is not None and not latest_df.empty:
                last_candle = latest_df.iloc[-1]
                c_close = last_candle.get('close', current_price)
                c_ema = last_candle.get('EMA_50', 0.0)
                c_sma20 = last_candle.get('SMA_20', 0.0)
                lwma_10_l = last_candle.get('LWMA_10_Low', 0.0)
                lwma_10_h = last_candle.get('LWMA_10_High', 0.0)

                if pos.type == mt5.ORDER_TYPE_BUY:
                    # Syarat Batal ZZL (Slide 51-56): Close menembus di bawah EMA 50
                    if c_ema > 0 and c_close < c_ema:
                        reversal_detected = True
                        reversal_reason = f"Thesis Invalidation: Close ({c_close:.2f}) < EMA 50 ({c_ema:.2f})"
                    # Konfirmasi CSAK/CSM Sell Lawan Arah (Slide 31): Close < Mid BB dan < LWMA 10 Low
                    elif c_sma20 > 0 and lwma_10_l > 0 and c_close < c_sma20 and c_close < lwma_10_l:
                        reversal_detected = True
                        reversal_reason = f"Opposite CSAK Sell: Close ({c_close:.2f}) < Mid BB ({c_sma20:.2f}) & LWMA 10 Low ({lwma_10_l:.2f})"
                    # AI Signal Surge ke arah lawan
                    elif p_sell_rev >= 0.70:
                        reversal_detected = True
                        reversal_reason = f"AI Reversal Surge: Prob SELL {p_sell_rev*100:.0f}%"

                elif pos.type == mt5.ORDER_TYPE_SELL:
                    # Syarat Batal ZZL (Slide 51-56): Close menembus di atas EMA 50
                    if c_ema > 0 and c_close > c_ema:
                        reversal_detected = True
                        reversal_reason = f"Thesis Invalidation: Close ({c_close:.2f}) > EMA 50 ({c_ema:.2f})"
                    # Konfirmasi CSAK/CSM Buy Lawan Arah (Slide 31): Close > Mid BB dan > LWMA 10 High
                    elif c_sma20 > 0 and lwma_10_h > 0 and c_close > c_sma20 and c_close > lwma_10_h:
                        reversal_detected = True
                        reversal_reason = f"Opposite CSAK Buy: Close ({c_close:.2f}) > Mid BB ({c_sma20:.2f}) & LWMA 10 High ({lwma_10_h:.2f})"
                    # AI Signal Surge ke arah lawan
                    elif p_buy_rev >= 0.70:
                        reversal_detected = True
                        reversal_reason = f"AI Reversal Surge: Prob BUY {p_buy_rev*100:.0f}%"

            if reversal_detected:
                logging.warning(
                    f"[REVERSAL EXIT] ⚠️ Sinyal Pembalikan terdeteksi untuk tiket #{ticket} ({mode}): "
                    f"{reversal_reason}. Menjalankan Full Close."
                )
                success = self.order_router.execute_full_close(ticket, reason=f"Rev: {reversal_reason}", symbol=symbol)
                if success:
                    self.initial_risks.pop(ticket, None)
                    self.position_modes.pop(ticket, None)
                continue

            # =========================================================================
            # 2. EVALUASI TARGET RISK:REWARD (RR) & MILESTONES
            # =========================================================================
            if not is_runner:
                # --- HIT_RUN LOGIC (Target RR 1:2) ---
                if current_r >= 1.0 and not is_already_be:
                    logging.info(f"[HIT_RUN] Target RR 1:1 tercapai ({current_r:.2f}R) untuk tiket #{ticket}. Geser SL ke BE.")
                    self.order_router.modify_sl_to_break_even(ticket, symbol)
                    
                if current_r >= 2.0:
                    logging.info(f"[HIT_RUN] 🎯 Target RR 1:2 tercapai ({current_r:.2f}R) untuk tiket #{ticket}. Menjalankan Full Close.")
                    success = self.order_router.execute_full_close(
                        ticket, 
                        reason=f"Hit&Run RR 1:2 TP ({current_r:.1f}R)", 
                        symbol=symbol
                    )
                    if success:
                        self.initial_risks.pop(ticket, None)
                        self.position_modes.pop(ticket, None)
                    continue
            else:
                # --- RUNNER LOGIC ---
                # 1. Milestone 1:2 -> Partial close 50% & BE at 2R
                if current_r >= 2.0:
                    if not is_already_be:
                        logging.info(f"[RUNNER] Milestone RR 1:2 tercapai ({current_r:.2f}R) untuk tiket #{ticket}. Partial Close 50% & SL ke BE.")
                        self.order_router.execute_partial_close_50(ticket, symbol)
                        self.order_router.modify_sl_to_break_even(ticket, symbol)

                # 2. Maximum learned RR Exit
                max_runner_rr = getattr(self.researcher, 'max_runner_rr', 5.0) if self.researcher else 5.0
                if current_r >= max_runner_rr:
                    logging.info(f"[RUNNER EXIT] 🎯 Maximum RR ({max_runner_rr:.1f}R) tercapai ({current_r:.2f}R) untuk tiket #{ticket}. Menjalankan Full Close.")
                    success = self.order_router.execute_full_close(
                        ticket, 
                        reason=f"Runner Max RR ({max_runner_rr:.1f}R)", 
                        symbol=symbol
                    )
                    if success:
                        self.initial_risks.pop(ticket, None)
                        self.position_modes.pop(ticket, None)
                    continue
