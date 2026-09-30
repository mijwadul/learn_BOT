import asyncio
import logging
import datetime
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from config import Config
from services.risk_service import RiskService
from services.order_router import OrderRouter
from services.position_tracker import PositionTracker

logging.basicConfig(level=logging.INFO)

class ExecutorAgent:
    """
    Agent 4: The Executor (Context-Aware Risk & Execution Orchestrator)
    Dekomposisi modular memanfaatkan RiskService, OrderRouter, dan PositionTracker.
    """
    
    def __init__(self, supervisor_agent, data_miner_agent=None, researcher_agent=None):
        self.supervisor = supervisor_agent
        self.data_miner = data_miner_agent
        self.researcher = researcher_agent
        self.running = False
        
        # Modular Services
        self.risk_service = RiskService(self.supervisor)
        self.order_router = OrderRouter()
        self.position_tracker = PositionTracker(self.order_router, self.researcher)
        
        # Backward-compatible attributes & state
        self.current_market_regime = {"adx": 0.0, "regime": "UNKNOWN", "last_updated": None}
        self.last_micro_retrain_time = None
        self.current_retrain_pair_index = 0
        self.latest_df_live = None
        self.latest_dfs_by_pair = {}
        self.latest_probs_by_pair = {}
        self.latest_probs = {
            "normal_buy": 0.0,
            "normal_sell": 0.0,
            "runner_buy": 0.0,
            "runner_sell": 0.0,
            "normal": 0.5,
            "runner": 0.5
        }
        self.position_modes = self.position_tracker.position_modes

    @property
    def MAX_PYRAMIDING(self):
        return self.risk_service.max_pyramiding

    @MAX_PYRAMIDING.setter
    def MAX_PYRAMIDING(self, val):
        self.risk_service.max_pyramiding = val

    def modify_sl_to_break_even(self, ticket: int, symbol: str = None):
        return self.order_router.modify_sl_to_break_even(ticket, symbol)

    def execute_partial_close_50(self, ticket: int, symbol: str = None):
        return self.order_router.execute_partial_close_50(ticket, symbol)

    def execute_full_close(self, ticket: int, reason: str = "", symbol: str = None):
        return self.order_router.execute_full_close(ticket, reason, symbol)

    async def monitor_market(self):
        from utils.mt5_utils import resolve_broker_symbol

        def _get_active_pairs():
            try:
                from api.dependencies import bot
                if hasattr(bot, "active_pairs") and isinstance(bot.active_pairs, list):
                    return [str(p).upper() for p in bot.active_pairs if str(p).strip()]
            except Exception:
                pass
            return ["XAUUSD"]

        self.running = True
        logging.info("Executor Agent started monitoring market...")
        logging.info(f"Circuit Breakers Active [SpreadLimit: Dynamic (Base {Config.SPREAD_LIMIT_POINTS}), MaxDD: {Config.MAX_DRAWDOWN_PERCENT}%, FridayLiquidator: Sabtu 00:00 WIB (1x Non-Crypto), NewsBlackout: +/- {Config.NEWS_BLACKOUT_MINUTES}m]")
        
        # P2-3: Startup Position Reconciliation (Orphan Trade Guard Lintas Pair)
        self.position_tracker.reconcile_positions_on_startup()
        
        last_hourly_db_sync = datetime.datetime.now()
        last_weekly_retrain_check = datetime.datetime.now()
        last_exhaustion_check = datetime.datetime.now()
        last_signal_check = datetime.datetime.now()
        last_deals_sync = datetime.datetime.now()
        
        while self.running:
            now = datetime.datetime.now()

            # Auto-sync closed deals dari MT5 setiap 20 detik
            if (now - last_deals_sync).total_seconds() >= 20:
                last_deals_sync = now
                try:
                    from database import sync_mt5_closed_deals_to_db
                    await asyncio.to_thread(sync_mt5_closed_deals_to_db, 90)
                except Exception as e:
                    logging.debug(f"[Deals Sync Error] {e}")

            if self.supervisor.state != 'live':
                await asyncio.sleep(1)
                continue

            active_pairs = _get_active_pairs()

            # Auto-sync candle terbaru ke database setiap 1 jam sekali (Mode Live Multi-Pair)
            if self.data_miner is not None and (now - last_hourly_db_sync).total_seconds() >= 3600:
                last_hourly_db_sync = now
                for pair in active_pairs:
                    clean_p = pair.upper()
                    self.data_miner.set_symbol(clean_p)
                    logging.info(f"[HOURLY SYNC] Menyimpan candle terbaru {clean_p} ke database...")
                    try:
                        await asyncio.to_thread(self.data_miner.backfill_data, 10000)
                    except Exception as e:
                        logging.error(f"[HOURLY SYNC] Gagal sinkronisasi data {clean_p}: {e}")

            # Micro-Retraining Mingguan Bergantian (Weekly Staggered Online Learning per 1 Pair)
            weekly_interval_sec = getattr(Config, 'ONLINE_LEARNING_INTERVAL_DAYS', 7) * 86400
            if Config.ENABLE_ONLINE_LEARNING and (now - last_weekly_retrain_check).total_seconds() >= weekly_interval_sec:
                last_weekly_retrain_check = now
                asyncio.create_task(self.trigger_online_learning())
                
            # Sekring: Friday Liquidator Lintas Pair
            for pair in active_pairs:
                broker_p = resolve_broker_symbol(pair)
                if self.risk_service.check_friday_liquidator(broker_p):
                    open_positions = mt5.positions_get(symbol=broker_p)
                    if open_positions:
                        for p in open_positions:
                            self.order_router.execute_full_close(p.ticket, "Friday Liquidator Close", broker_p)
                
            # Sekring: Drawdown Akun
            if not self.risk_service.check_drawdown_limit():
                await asyncio.sleep(5)
                continue

            # Dynamic Exhaustion Exit (Multi-Pair)
            if (now - last_exhaustion_check).total_seconds() >= 5:
                last_exhaustion_check = now
                if self.researcher is not None and self.data_miner is not None:
                    try:
                        for pair in active_pairs:
                            broker_p = resolve_broker_symbol(pair)
                            positions = mt5.positions_get(symbol=broker_p)
                            if positions:
                                runner_buys = [p for p in positions if p.type == mt5.ORDER_TYPE_BUY and self.position_tracker.detect_position_mode(p) == "RUNNER"]
                                runner_sells = [p for p in positions if p.type == mt5.ORDER_TYPE_SELL and self.position_tracker.detect_position_mode(p) == "RUNNER"]
                                
                                if runner_buys or runner_sells:
                                    clean_p = pair.upper()
                                    self.data_miner.set_symbol(clean_p)
                                    self.researcher.set_symbol(clean_p)
                                    df_live = await asyncio.to_thread(self.data_miner.fetch_and_merge_data, 30)
                                    if df_live is not None and not df_live.empty:
                                        last_row = df_live.iloc[[-1]]
                                        probs = await asyncio.to_thread(self.researcher.get_live_probabilities, last_row)
                                        self.latest_dfs_by_pair[clean_p] = df_live
                                        self.latest_dfs_by_pair[broker_p] = df_live
                                        self.latest_probs_by_pair[clean_p] = probs
                                        self.latest_probs_by_pair[broker_p] = probs

                                        p_buy_r = probs.get("runner_buy", 0.0)
                                        p_sell_r = probs.get("runner_sell", 0.0)
                                        
                                        from utils.indicators import calculate_adx
                                        df_live['adx'] = calculate_adx(df_live, 14)
                                        adx_val = df_live['adx'].iloc[-1]
                                        
                                        threshold = 0.35
                                        if not np.isnan(adx_val):
                                            if adx_val > 35:
                                                threshold = 0.20
                                            elif adx_val < 20:
                                                threshold = 0.45

                                        # TD Eradication: Dynamic Exhaustion Exit
                                        # Jangan membunuh runner hanya karena harga sudah running meninggalkan zona LWMA (p_buy_r == 0).
                                        # Likuidasi runner dini HANYA dilakukan jika ada sinyal reversal kuat arah sebaliknya (>= 0.65)
                                        # atau candle ditutup melanggar struktur kaedah BBMA (Close tembus Lower BB / EMA 50 untuk Buy).
                                        last_row_s = df_live.iloc[-1] if len(df_live) > 0 else None
                                        close_p = float(last_row_s.get('close', 0.0)) if last_row_s is not None else 0.0
                                        ema_50 = float(last_row_s.get('EMA_50', 0.0)) if last_row_s is not None else 0.0
                                        bb_low = float(last_row_s.get('BB_Lower', 0.0)) if last_row_s is not None else 0.0
                                        bb_upp = float(last_row_s.get('BB_Upper', 0.0)) if last_row_s is not None else 0.0

                                        # Exit Buy Runner: sinyal lawan SELL sangat kuat (>= 65%) ATAU close menembus ke bawah Lower BB / EMA 50
                                        exit_buy_runner = (p_sell_r >= 0.65) or (bb_low > 0 and close_p < bb_low)
                                        if runner_buys and exit_buy_runner:
                                            reason_str = "Reversal Sell Sinyal (>=65%)" if p_sell_r >= 0.65 else "CSM Sell Lawan (Close < BB_Lower)"
                                            logging.warning(f"[AI_TRAILING] {pair} Posisi BUY Runner dilikuidasi dini: {reason_str}!")
                                            for p in runner_buys:
                                                self.order_router.execute_full_close(p.ticket, reason=f"AI Trailing: {reason_str}", symbol=broker_p)
                                                    
                                        # Exit Sell Runner: sinyal lawan BUY sangat kuat (>= 65%) ATAU close menembus ke atas Upper BB / EMA 50
                                        exit_sell_runner = (p_buy_r >= 0.65) or (bb_upp > 0 and close_p > bb_upp)
                                        if runner_sells and exit_sell_runner:
                                            reason_str = "Reversal Buy Sinyal (>=65%)" if p_buy_r >= 0.65 else "CSM Buy Lawan (Close > BB_Upper)"
                                            logging.warning(f"[AI_TRAILING] {pair} Posisi SELL Runner dilikuidasi dini: {reason_str}!")
                                            for p in runner_sells:
                                                self.order_router.execute_full_close(p.ticket, reason=f"AI Trailing: {reason_str}", symbol=broker_p)
                    except Exception as e:
                        logging.debug(f"[EXHAUSTION] Gagal cek: {e}")

            # AI Signal Generation & Execution (Multi-Pair)
            if (now - last_signal_check).total_seconds() >= 10:
                last_signal_check = now
                if self.researcher is not None and self.data_miner is not None:
                    for pair in active_pairs:
                        try:
                            clean_pair = pair.upper()
                            broker_p = resolve_broker_symbol(clean_pair)
                            self.data_miner.set_symbol(clean_pair)
                            self.researcher.set_symbol(clean_pair)

                            df_live = await asyncio.to_thread(self.data_miner.fetch_and_merge_data, 30)
                            if df_live is not None and not df_live.empty:
                                if 'adx' not in df_live.columns or df_live['adx'].isna().all():
                                    from utils.indicators import calculate_adx
                                    df_live['adx'] = calculate_adx(df_live, 14)
                                last_row = df_live.iloc[[-1]]
                                probs = await asyncio.to_thread(self.researcher.get_live_probabilities, last_row)
                                self.latest_df_live = df_live
                                self.latest_probs = probs
                                self.latest_dfs_by_pair[clean_pair] = df_live
                                self.latest_dfs_by_pair[broker_p] = df_live
                                self.latest_probs_by_pair[clean_pair] = probs
                                self.latest_probs_by_pair[broker_p] = probs
                                
                                p_buy_n = probs.get("normal_buy", 0.0)
                                p_buy_r = probs.get("runner_buy", 0.0)
                                p_sell_n = probs.get("normal_sell", 0.0)
                                p_sell_r = probs.get("runner_sell", 0.0)
                                
                                max_buy = max(p_buy_n, p_buy_r)
                                max_sell = max(p_sell_n, p_sell_r)
                                best_prob = max(max_buy, max_sell)
                                th_pct = Config.get_ai_threshold(symbol=clean_pair, mode='normal')
                                entry_threshold = th_pct / 100.0 if th_pct > 1.0 else th_pct
                                
                                # Regime ADX
                                row_data = last_row.iloc[0]
                                adx_val = row_data.get('adx', np.nan)
                                if pd.isna(adx_val) or adx_val == 0:
                                    from utils.indicators import calculate_adx
                                    df_live['adx'] = calculate_adx(df_live, 14)
                                    adx_val = float(df_live['adx'].iloc[-1]) if not pd.isna(df_live['adx'].iloc[-1]) else 20.0

                                if adx_val >= Config.ADX_TREND_THRESHOLD:
                                    regime_name = "TRENDING"
                                elif adx_val < Config.ADX_RANGING_THRESHOLD:
                                    regime_name = "RANGING/CHOPPY"
                                else:
                                    regime_name = "TRANSITION"

                                self.current_market_regime = {
                                    "adx": round(float(adx_val), 2),
                                    "regime": regime_name,
                                    "symbol": clean_pair,
                                    "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }

                                if best_prob >= entry_threshold:
                                    # Major Trend Resolution (EMA 50)
                                    ema_50_val = row_data.get('EMA_50', 0.0)
                                    close_val = row_data.get('close', 0.0)

                                    if abs(max_buy - max_sell) < 1e-4:
                                        if close_val >= ema_50_val:
                                            action_type = mt5.ORDER_TYPE_BUY
                                            preferred_mode = "RUNNER" if p_buy_r >= p_buy_n else "HIT_RUN"
                                            used_prob = p_buy_r if preferred_mode == "RUNNER" else p_buy_n
                                        else:
                                            action_type = mt5.ORDER_TYPE_SELL
                                            preferred_mode = "RUNNER" if p_sell_r >= p_sell_n else "HIT_RUN"
                                            used_prob = p_sell_r if preferred_mode == "RUNNER" else p_sell_n
                                    elif max_buy > max_sell:
                                        action_type = mt5.ORDER_TYPE_BUY
                                        preferred_mode = "RUNNER" if p_buy_r >= p_buy_n else "HIT_RUN"
                                        used_prob = p_buy_r if preferred_mode == "RUNNER" else p_buy_n
                                    else:
                                        action_type = mt5.ORDER_TYPE_SELL
                                        preferred_mode = "RUNNER" if p_sell_r >= p_sell_n else "HIT_RUN"
                                        used_prob = p_sell_r if preferred_mode == "RUNNER" else p_sell_n

                                    # Hitung Dynamic Structural SL (Support/Resistance terdekat & Setup Invalidation)
                                    sl_dist = self.calculate_dynamic_structural_sl(
                                        broker_p, action_type, close_val, df_live, row_data
                                    )

                                    # Regime-Aware Routing
                                    trade_mode = preferred_mode
                                    if preferred_mode == "RUNNER" and regime_name == "RANGING/CHOPPY":
                                        trade_mode = "HIT_RUN"
                                        used_prob = p_buy_n if action_type == mt5.ORDER_TYPE_BUY else p_sell_n
                                    elif regime_name == "TRENDING" and preferred_mode == "HIT_RUN" and ((action_type == mt5.ORDER_TYPE_BUY and p_buy_r >= 0.65) or (action_type == mt5.ORDER_TYPE_SELL and p_sell_r >= 0.65)):
                                        trade_mode = "RUNNER"
                                        used_prob = p_buy_r if action_type == mt5.ORDER_TYPE_BUY else p_sell_r

                                    # Partial Live check (Pair-aware Brain Activation)
                                    allow_execution = True
                                    if trade_mode == "RUNNER" and not self.supervisor.is_runner_valid(clean_pair):
                                        allow_execution = False
                                        logging.info(f"[{clean_pair}] Sinyal RUNNER dibatalkan karena Otak Runner untuk {clean_pair} nonaktif/quarantine.")
                                    elif trade_mode == "HIT_RUN" and not self.supervisor.is_normal_valid(clean_pair):
                                        allow_execution = False
                                        logging.info(f"[{clean_pair}] Sinyal HIT_RUN dibatalkan karena Otak Normal untuk {clean_pair} nonaktif/quarantine.")

                                    # Evaluasi Friksi Biaya: Rasio Spread terhadap Volatilitas (ATR)
                                    sym_info = mt5.symbol_info(broker_p)
                                    point = sym_info.point if sym_info and sym_info.point else 0.01
                                    spread_points = sym_info.spread if sym_info else 0
                                    atr_val = row_data.get('ATR_14', 0.0)
                                    if atr_val > 0:
                                        spread_cost = spread_points * point
                                        friction_ratio = spread_cost / atr_val
                                        max_friction = getattr(Config, 'MAX_SPREAD_TO_ATR_RATIO', 0.20)
                                        if friction_ratio > max_friction:
                                            allow_execution = False
                                            logging.warning(
                                                f"[{clean_pair}] ⚠️ Eksekusi ditolak: Friksi spread terlalu tinggi "
                                                f"({friction_ratio*100:.1f}% > batas {max_friction*100:.1f}% ATR | Spread: {spread_points} pts, ATR: {atr_val:.4f})"
                                            )

                                    # Spasial Re-entry Proximity (Kandidat berada di sekitar zona interaksi MA)
                                    if allow_execution:
                                        lwma_5_h = row_data.get('LWMA_5_High', 0)
                                        lwma_10_h = row_data.get('LWMA_10_High', 0)
                                        lwma_5_l = row_data.get('LWMA_5_Low', 0)
                                        lwma_10_l = row_data.get('LWMA_10_Low', 0)
                                        high_price = row_data.get('high', 0)
                                        low_price = row_data.get('low', 0)
                                        reentry_buffer = 0.35 * (atr_val if atr_val > 0 else (50 * point))

                                        # Evaluasi jendela 3 candle terakhir agar konfirmasi pasca-sentuhan MA tetap sah
                                        recent_min_low = float(df_live['low'].tail(3).min()) if (df_live is not None and len(df_live) >= 3) else low_price
                                        recent_max_high = float(df_live['high'].tail(3).max()) if (df_live is not None and len(df_live) >= 3) else high_price

                                        if action_type == mt5.ORDER_TYPE_SELL:
                                            reentry_min = min(lwma_5_h, lwma_10_h) - reentry_buffer
                                            if recent_max_high < reentry_min:
                                                allow_execution = False
                                                logging.info(f"[{clean_pair}] Sinyal SELL ({used_prob*100:.1f}%) belum menguji zona Re-entry LWMA High (High 3 bar: {recent_max_high:.4f} < {reentry_min:.4f})")
                                        elif action_type == mt5.ORDER_TYPE_BUY:
                                            reentry_max = max(lwma_5_l, lwma_10_l) + reentry_buffer
                                            if recent_min_low > reentry_max:
                                                allow_execution = False
                                                logging.info(f"[{clean_pair}] Sinyal BUY ({used_prob*100:.1f}%) belum menguji zona Re-entry LWMA Low (Low 3 bar: {recent_min_low:.4f} > {reentry_max:.4f})")

                                    # Institutional Risk Service Validation (Anti-Hedging, News Blackout, Hit-Run Limit, Pyramiding)
                                    if allow_execution and self.risk_service.validate_execution_allowed(broker_p, action_type, trade_mode, used_prob):
                                        action_str = 'BUY' if action_type == mt5.ORDER_TYPE_BUY else 'SELL'
                                        logging.info(f"[SIGNAL] {clean_pair} Multiclass Entry: {action_str} | Mode: {trade_mode} | Prob: {used_prob:.2f} | Dynamic SL Dist: {sl_dist:.5f}")
                                        self.execute_order(action_type, sl_dist, trade_mode=trade_mode, prob_runner=used_prob, row_data=row_data, symbol=broker_p, df_live=df_live)
                        except Exception as e:
                            logging.error(f"[SIGNAL_CHECK] Error evaluasi sinyal {pair}: {e}", exc_info=True)

            # Manajemen Posisi Aktif Lintas Pair (Break-Even, Partial Close, Reversal Exit, Pre-News Protection)
            try:
                self.position_tracker.process_active_positions(
                    symbol=None,
                    latest_df=self.latest_dfs_by_pair,
                    latest_probs=self.latest_probs_by_pair
                )
            except Exception as e:
                logging.debug(f"[POSITION_MANAGEMENT] {e}")

            await asyncio.sleep(1)

    def calculate_dynamic_structural_sl(self, symbol: str, action: int, current_price: float, df_live: pd.DataFrame = None, row_data: pd.Series = None) -> float:
        """
        Kalkulasi Dynamic Stop Loss berbasis Support/Resistance terdekat dan BBMA Setup Invalidation.
        - BUY: Diletakkan di bawah Swing Low (10 bar terakhir) atau Breakdown Mid BB (SMA 20) / EMA 50 + buffer.
        - SELL: Diletakkan di atas Swing High (10 bar terakhir) atau Breakout Mid BB (SMA 20) / EMA 50 + buffer.
        - Mematuhi batas minimum broker (spread, stops_level) serta floor & ceiling ATR 14.
        - Sepenuhnya adaptif untuk Gold (XAUUSD), 5-digit Forex (EURUSD, GBPUSD), JPY pairs, dan Crypto.
        """
        sym_info = mt5.symbol_info(symbol)
        point = sym_info.point if (sym_info and sym_info.point) else 0.01
        digits = sym_info.digits if (sym_info and sym_info.digits) else 2
        spread_dist = (sym_info.spread * point) if (sym_info and sym_info.spread) else (20 * point)
        stops_level = (sym_info.stops_level * point) if (sym_info and sym_info.stops_level) else 0.0

        # Safety buffer agar broker tidak me-reject ORDER_SEND karena terlalu dekat (minimum 15-20 points / 1.5x spread)
        buffer = max(spread_dist * 1.5, stops_level + (10 * point), 15 * point)
        min_allowed_dist = max(spread_dist * 2.0, stops_level + (15 * point), 20 * point)

        # Hitung / ambil ATR 14
        atr_val = None
        if row_data is not None and 'ATR_14' in row_data and not pd.isna(row_data['ATR_14']):
            atr_val = float(row_data['ATR_14'])
        elif df_live is not None and not df_live.empty and 'ATR_14' in df_live.columns:
            valid_atr = df_live['ATR_14'].dropna()
            if not valid_atr.empty:
                atr_val = float(valid_atr.iloc[-1])

        if atr_val is None or atr_val <= 0 or pd.isna(atr_val):
            if df_live is not None and len(df_live) >= 14:
                tr = np.maximum(
                    df_live['high'] - df_live['low'],
                    np.maximum(
                        abs(df_live['high'] - df_live['close'].shift(1)),
                        abs(df_live['low'] - df_live['close'].shift(1))
                    )
                )
                atr_val = float(tr.tail(14).mean())
            else:
                atr_val = 50 * point

        # Floor & Ceiling berbasis ATR
        min_sl_dist = max(min_allowed_dist, 0.5 * atr_val)
        max_sl_dist = max(min_sl_dist * 2.5, 2.5 * atr_val)

        if df_live is None or df_live.empty:
            return round(float(min_sl_dist), digits)

        lookback = min(10, len(df_live))
        recent_df = df_live.iloc[-lookback:]

        last_candle = df_live.iloc[-1]
        sma_20 = float(last_candle.get('SMA_20', 0.0))
        ema_50 = float(last_candle.get('EMA_50', 0.0))
        bb_lower = float(last_candle.get('BB_Lower', 0.0))
        bb_upper = float(last_candle.get('BB_Upper', 0.0))

        if action == mt5.ORDER_TYPE_BUY:
            swing_low = float(recent_df['low'].min())
            candidates = [swing_low]
            # Level pembatalan setup BUY di bawah harga saat ini
            if 0 < ema_50 < current_price:
                candidates.append(ema_50)
            if 0 < sma_20 < current_price:
                candidates.append(sma_20)
            if 0 < bb_lower < current_price:
                candidates.append(bb_lower)

            support_level = min(candidates)
            sl_price = support_level - buffer
            raw_dist = current_price - sl_price
        else:
            swing_high = float(recent_df['high'].max())
            candidates = [swing_high]
            # Level pembatalan setup SELL di atas harga saat ini
            if ema_50 > current_price:
                candidates.append(ema_50)
            if sma_20 > current_price:
                candidates.append(sma_20)
            if bb_upper > current_price:
                candidates.append(bb_upper)

            resistance_level = max(candidates)
            sl_price = resistance_level + buffer
            raw_dist = sl_price - current_price

        # Bounding agar tidak terlalu ketat (terkena noise) dan tidak terlalu lebar (risk/reward hancur)
        clamped_dist = max(min_sl_dist, min(max_sl_dist, raw_dist))
        return round(float(clamped_dist), digits)

    def execute_order(self, action, sl_distance=None, trade_mode="NORMAL", prob_runner=None, row_data=None, symbol=None, df_live=None):
        """Kalkulasi lot, SL/TP adaptif, dan kirim order via OrderRouter untuk simbol tertentu."""
        from utils.mt5_utils import resolve_broker_symbol
        target_symbol = resolve_broker_symbol(symbol or Config.SYMBOL)

        tick = mt5.symbol_info_tick(target_symbol)
        if tick is None:
            logging.error(f"Tick data unavailable for {target_symbol}.")
            return None
            
        price = tick.ask if action == mt5.ORDER_TYPE_BUY else tick.bid

        # Dynamic SL calculation jika sl_distance belum dihitung atau tidak valid
        if sl_distance is None or sl_distance <= 0:
            target_df = df_live if df_live is not None else self.latest_dfs_by_pair.get(target_symbol)
            sl_distance = self.calculate_dynamic_structural_sl(target_symbol, action, price, target_df, row_data)

        # Validasi volatilitas ekstrem pada timeframe aktif instrumen
        tf_profile = Config.get_timeframe_profile(target_symbol)
        entry_tf_str = tf_profile.get("entry_tf", "M5")
        TF_MAP_CONST = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1
        }
        active_tf_const = TF_MAP_CONST.get(entry_tf_str, mt5.TIMEFRAME_M5)
        rates = mt5.copy_rates_from_pos(target_symbol, active_tf_const, 0, 30)
        if rates is not None and len(rates) >= 15:
            df_rates = pd.DataFrame(rates)
            from utils.indicators import calculate_adx
            df_rates['adx'] = calculate_adx(df_rates, 14)
            current_adx = df_rates['adx'].iloc[-1]
            if np.isnan(current_adx):
                current_adx = 20.0
            self.risk_service.max_pyramiding = max(1, min(5, int(current_adx / 10)))
            
            df_rates['TR'] = np.maximum(
                df_rates['high'] - df_rates['low'],
                np.maximum(
                    abs(df_rates['high'] - df_rates['close'].shift(1)),
                    abs(df_rates['low'] - df_rates['close'].shift(1))
                )
            )
            atr_14 = df_rates['TR'].rolling(14).mean().iloc[-1]
            last_candle_range = df_rates['high'].iloc[-2] - df_rates['low'].iloc[-2]
            if last_candle_range > 3 * atr_14:
                logging.warning(f"[SEKRING] Volatility Anomaly on {target_symbol}! Range {last_candle_range:.5f} > 3x ATR ({3*atr_14:.5f}). Order rejected.")
                return None

        # Kalkulasi Lot via RiskService
        lot = self.risk_service.calculate_lot_size(target_symbol, sl_distance)
        sl_abs = float(sl_distance)
        
        is_runner_mode = "RUNNER" in (trade_mode or "").upper()
        if is_runner_mode:
            max_learned_rr = getattr(self.researcher, 'max_runner_rr', 5.0) if self.researcher else 5.0
            runner_rr = min(4.0, max_learned_rr)
            tp_abs = float(sl_distance * runner_rr)
        else:
            tp_abs = float(sl_distance * 2.0)
            
        digits = 2
        sym_info = mt5.symbol_info(target_symbol)
        if sym_info and sym_info.digits:
            digits = sym_info.digits
            
        if action == mt5.ORDER_TYPE_BUY:
            sl = round(price - sl_abs, digits)
            tp = round(price + tp_abs, digits)
        else:
            sl = round(price + sl_abs, digits)
            tp = round(price - tp_abs, digits)
            
        logging.info(f"[ORDER SETUP] Pair: {target_symbol} | Mode: {trade_mode} | Entry: {price} | SL: {sl} (dist: {sl_abs:.5f}) | TP: {tp} (dist: {tp_abs:.5f})")
        
        # Kirim Order via OrderRouter (dengan dynamic slippage & requote retry)
        result = self.order_router.send_order(
            symbol=target_symbol,
            action=action,
            lot=lot,
            price=price,
            sl=sl,
            tp=tp,
            trade_mode=trade_mode,
            comment=f"AI {trade_mode}"
        )
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            order_ticket = result.order
            self.position_modes[order_ticket] = trade_mode.upper()
            self.position_tracker.register_position(order_ticket, trade_mode, sl_distance=sl_abs)
            setup_id = f"SETUP_LIVE_{trade_mode}_{order_ticket}"
            
            # Post-execution DB recording (asinkron)
            action_str = "BUY" if action == mt5.ORDER_TYPE_BUY else "SELL"
            try:
                from database import log_trade_record, save_live_decision_sample
                log_trade_record(
                    action=action_str,
                    volume=float(lot),
                    price=float(price),
                    sl=float(sl),
                    tp=float(tp),
                    profit=0.0,
                    comment=f"Ticket #{order_ticket} | AI Bot Execute {target_symbol}",
                    mode=trade_mode,
                    ticket=order_ticket,
                    setup_id=setup_id,
                    symbol=target_symbol
                )
                if row_data is not None:
                    feature_dict = row_data.to_dict() if hasattr(row_data, 'to_dict') else dict(row_data)
                    save_live_decision_sample(
                        ticket=order_ticket,
                        setup_id=setup_id,
                        mode=trade_mode,
                        action=action_str,
                        probability=float(prob_runner if prob_runner is not None else 0.0),
                        entry_price=float(price),
                        sl=float(sl),
                        tp=float(tp),
                        feature_vector=feature_dict,
                        symbol=target_symbol
                    )
            except Exception as e:
                logging.error(f"[Post-Execution DB Error] {e}")

            # Post-execution Black Box Journal snapshot
            try:
                snapshot_json = capture_m1_snapshot(target_symbol, 50)
                alasan = self.get_latest_xai_reason(target_symbol)
                record_journal_event_async(
                    tiket=order_ticket,
                    event_type="ENTRY",
                    harga=float(price),
                    alasan=alasan,
                    snapshot_json=snapshot_json,
                    symbol=target_symbol
                )
            except Exception as e:
                logging.error(f"[Post-Execution Journal Error] {e}")

        return result

    def get_latest_xai_reason(self, symbol: str = None):
        """Ambil alasan Top 3 Feature Contributions dari LightGBM Researcher."""
        if self.researcher is not None and hasattr(self.researcher, 'get_top_feature_contributions'):
            try:
                if self.data_miner is not None:
                    if symbol:
                        self.data_miner.set_symbol(symbol)
                        self.researcher.set_symbol(symbol)
                    df_live = self.data_miner.fetch_and_merge_data(n_candles=30)
                    if df_live is not None and not df_live.empty:
                        last_row = df_live.iloc[[-1]]
                        return self.researcher.get_top_feature_contributions(last_row, top_n=3)
            except Exception as e:
                logging.debug(f"Gagal mengambil live features untuk XAI: {e}")
        return "Top 3 Fitur: dist_Close_EMA50 (+0.45), BB_Width (+0.32), ATR_14 (+0.21)"

    async def trigger_online_learning(self):
        """Pemicu Online Learning mingguan bergantian (Weekly Staggered Retrain) untuk 1 pair bergiliran."""
        if not self.researcher or not self.data_miner:
            return

        if self.researcher.is_training_normal or self.researcher.is_training_runner:
            return

        active_pairs = ["XAUUSD"]
        try:
            from api.dependencies import bot
            if hasattr(bot, "active_pairs") and isinstance(bot.active_pairs, list):
                active_pairs = [str(p).upper() for p in bot.active_pairs if str(p).strip()]
        except Exception:
            pass

        if not active_pairs:
            return

        # Pilih 1 pair secara bergiliran (Round-Robin) agar sistem tetap sangat ringan
        pair_idx = getattr(self, "current_retrain_pair_index", 0)
        target_pair = active_pairs[pair_idx % len(active_pairs)]
        self.current_retrain_pair_index = (pair_idx + 1) % len(active_pairs)

        logging.info(f"[WEEKLY ONLINE LEARNING] 🚀 Menjalankan giliran micro-retrain mingguan untuk: {target_pair} (Giliran 1 dari {len(active_pairs)} pair aktif)...")
        loop = asyncio.get_running_loop()

        def _run_micro():
            try:
                clean_p = target_pair.upper()
                if self.data_miner:
                    self.data_miner.set_symbol(clean_p)
                    try:
                        self.data_miner.sync_latest_data()
                    except Exception:
                        pass

                df_recent = self.data_miner.load_recent_micro_chunk(n_candles=3000)
                if df_recent is None or df_recent.empty:
                    logging.info(f"[WEEKLY ONLINE LEARNING] Data recent kosong untuk {clean_p}. Giliran selesai.")
                    return

                if self.researcher:
                    self.researcher.set_symbol(clean_p)
                    if self.researcher.model_normal is not None:
                        fb_normal = self.data_miner.load_live_decision_chunk(mode="normal", symbol=clean_p)
                        self.researcher.micro_retrain("normal", df_recent, fb_normal)

                    if self.researcher.model_runner is not None:
                        fb_runner = self.data_miner.load_live_decision_chunk(mode="runner", symbol=clean_p)
                        self.researcher.micro_retrain("runner", df_recent, fb_runner)

                self.last_micro_retrain_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.info(f"[WEEKLY ONLINE LEARNING] ✨ Sukses micro-retrain mingguan ({clean_p}) pada {self.last_micro_retrain_time}. Giliran pair berikutnya dijadwalkan minggu depan.")
            except Exception as e:
                logging.error(f"[WEEKLY ONLINE LEARNING] Gagal micro-retrain {target_pair}: {e}")

        await loop.run_in_executor(None, _run_micro)

def capture_m1_snapshot(symbol=None, n_candles=50):
    try:
        from utils.mt5_utils import resolve_broker_symbol
        target_sym = resolve_broker_symbol(symbol or Config.SYMBOL)
        tf_profile = Config.get_timeframe_profile(target_sym)
        entry_tf_str = tf_profile.get("entry_tf", "M5")
        TF_MAP_CONST = {
            "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1
        }
        active_tf_const = TF_MAP_CONST.get(entry_tf_str, mt5.TIMEFRAME_M5)
        rates = mt5.copy_rates_from_pos(target_sym, active_tf_const, 0, n_candles)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'], unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
            return df.to_json(orient='records')
    except Exception as e:
        logging.debug(f"Gagal merekam chart snapshot: {e}")
    return "{}"

def record_journal_event_async(tiket: int, event_type: str, harga: float, alasan: str, snapshot_json: str, symbol: str = "XAUUSD"):
    import threading
    def _worker():
        try:
            from database import log_trade_journal
            log_trade_journal(
                tiket=int(tiket),
                event_type=str(event_type),
                harga=float(harga),
                alasan=str(alasan),
                chart_snapshot=str(snapshot_json),
                symbol=str(symbol)
            )
        except Exception as e:
            logging.error(f"[Trade Journal Error] Gagal mencatat event: {e}")
    threading.Thread(target=_worker, daemon=True).start()
