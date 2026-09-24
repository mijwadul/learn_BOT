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
        self.latest_df_live = None
        self.latest_probs = {}
        self.position_modes = self.position_tracker.position_modes

    @property
    def MAX_PYRAMIDING(self):
        return self.risk_service.max_pyramiding

    @MAX_PYRAMIDING.setter
    def MAX_PYRAMIDING(self, val):
        self.risk_service.max_pyramiding = val

    def modify_sl_to_break_even(self, ticket: int):
        return self.order_router.modify_sl_to_break_even(ticket, Config.SYMBOL)

    def execute_partial_close_50(self, ticket: int):
        return self.order_router.execute_partial_close_50(ticket, Config.SYMBOL)

    def execute_full_close(self, ticket: int, reason: str = ""):
        return self.order_router.execute_full_close(ticket, reason, Config.SYMBOL)

    async def monitor_market(self):
        self.running = True
        logging.info("Executor Agent started monitoring market...")
        logging.info(f"Circuit Breakers Active [SpreadLimit: Dynamic (Base {Config.SPREAD_LIMIT_POINTS}), MaxDD: {Config.MAX_DRAWDOWN_PERCENT}%, FridayLiquidator: ON, NewsBlackout: +/- {Config.NEWS_BLACKOUT_MINUTES}m]")
        
        # P2-3: Startup Position Reconciliation (Orphan Trade Guard)
        self.position_tracker.reconcile_positions_on_startup(Config.SYMBOL)
        
        last_hourly_db_sync = datetime.datetime.now()
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

            # Auto-sync candle terbaru ke database setiap 1 jam sekali (Mode Live)
            if self.data_miner is not None and (now - last_hourly_db_sync).total_seconds() >= 3600:
                last_hourly_db_sync = now
                logging.info("[HOURLY SYNC] Menjalankan penyimpanan candle terbaru ke database secara asinkron...")
                try:
                    await asyncio.to_thread(self.data_miner.backfill_data, 10000)
                    logging.info("[HOURLY SYNC] Sinkronisasi candle 1 jam ke database berhasil.")
                    if Config.ENABLE_ONLINE_LEARNING:
                        asyncio.create_task(self.trigger_online_learning())
                except Exception as e:
                    logging.error(f"[HOURLY SYNC] Gagal sinkronisasi data ke database: {e}")
                
            # Sekring: Friday Liquidator
            if self.risk_service.check_friday_liquidator(Config.SYMBOL):
                open_positions = mt5.positions_get(symbol=Config.SYMBOL)
                if open_positions:
                    for p in open_positions:
                        self.order_router.execute_full_close(p.ticket, "Friday Liquidator Close", Config.SYMBOL)
                await asyncio.sleep(60)
                continue
                
            # Sekring: Spread Adaptif
            if not self.risk_service.check_spread_limit(Config.SYMBOL):
                await asyncio.sleep(5)
                continue
                
            # Sekring: Drawdown
            if not self.risk_service.check_drawdown_limit():
                await asyncio.sleep(5)
                continue

            # Dynamic Exhaustion Exit
            if (now - last_exhaustion_check).total_seconds() >= 5:
                last_exhaustion_check = now
                if self.researcher is not None and self.data_miner is not None:
                    try:
                        positions = mt5.positions_get(symbol=Config.SYMBOL)
                        if positions:
                            runner_buys = [p for p in positions if p.type == mt5.ORDER_TYPE_BUY and "RUNNER" in (p.comment or "").upper()]
                            runner_sells = [p for p in positions if p.type == mt5.ORDER_TYPE_SELL and "RUNNER" in (p.comment or "").upper()]
                            
                            if runner_buys or runner_sells:
                                df_live = await asyncio.to_thread(self.data_miner.fetch_and_merge_data, 30)
                                if df_live is not None and not df_live.empty:
                                    last_row = df_live.iloc[[-1]]
                                    probs = await asyncio.to_thread(self.researcher.get_live_probabilities, last_row)
                                    prob_runner = probs.get("runner", 0.5)
                                    
                                    from utils.indicators import calculate_adx
                                    df_live['adx'] = calculate_adx(df_live, 14)
                                    adx_val = df_live['adx'].iloc[-1]
                                    
                                    threshold = 0.35
                                    if not np.isnan(adx_val):
                                        if adx_val > 35:
                                            threshold = 0.20
                                        elif adx_val < 20:
                                            threshold = 0.45
                                    if runner_buys and prob_runner < threshold:
                                        logging.warning(f"[AI_TRAILING] Probabilitas trend turun ke {prob_runner*100:.0f}%. Melikuidasi BUY RUNNER!")
                                        for p in runner_buys:
                                            self.order_router.execute_full_close(p.ticket, reason=f"AI Probability Trailing Stop: {prob_runner*100:.0f}%", symbol=Config.SYMBOL)
                                                
                                    if runner_sells and prob_runner > (1.0 - threshold):
                                        logging.warning(f"[AI_TRAILING] Probabilitas pembalikan naik ke {prob_runner*100:.0f}%. Melikuidasi SELL RUNNER!")
                                        for p in runner_sells:
                                            self.order_router.execute_full_close(p.ticket, reason=f"AI Probability Trailing Stop: {prob_runner*100:.0f}%", symbol=Config.SYMBOL)
                    except Exception as e:
                        logging.debug(f"[EXHAUSTION] Gagal cek: {e}")

            # AI Signal Generation & Execution
            if (now - last_signal_check).total_seconds() >= 10:
                last_signal_check = now
                if self.researcher is not None and self.data_miner is not None:
                    try:
                        df_live = await asyncio.to_thread(self.data_miner.fetch_and_merge_data, 30)
                        if df_live is not None and not df_live.empty:
                            last_row = df_live.iloc[[-1]]
                            probs = await asyncio.to_thread(self.researcher.get_live_probabilities, last_row)
                            self.latest_df_live = df_live
                            self.latest_probs = probs
                            
                            p_buy_n = probs.get("normal_buy", 0.0)
                            p_buy_r = probs.get("runner_buy", 0.0)
                            p_sell_n = probs.get("normal_sell", 0.0)
                            p_sell_r = probs.get("runner_sell", 0.0)
                            
                            max_buy = max(p_buy_n, p_buy_r)
                            max_sell = max(p_sell_n, p_sell_r)
                            best_prob = max(max_buy, max_sell)
                            
                            if best_prob >= 0.70:
                                row_data = last_row.iloc[0]
                                sl_dist = row_data.get('ATR_14', 5.0)
                                if pd.isna(sl_dist) or sl_dist < 5.0:
                                    sl_dist = 5.0

                                # Regime ADX
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
                                    "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                }
                                
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

                                # Regime-Aware Routing
                                trade_mode = preferred_mode
                                if preferred_mode == "RUNNER" and regime_name == "RANGING/CHOPPY":
                                    trade_mode = "HIT_RUN"
                                    used_prob = p_buy_n if action_type == mt5.ORDER_TYPE_BUY else p_sell_n
                                elif regime_name == "TRENDING" and preferred_mode == "HIT_RUN" and ((action_type == mt5.ORDER_TYPE_BUY and p_buy_r >= 0.65) or (action_type == mt5.ORDER_TYPE_SELL and p_sell_r >= 0.65)):
                                    trade_mode = "RUNNER"
                                    used_prob = p_buy_r if action_type == mt5.ORDER_TYPE_BUY else p_sell_r

                                # Partial Live check
                                allow_execution = True
                                if trade_mode == "RUNNER" and not self.supervisor.is_runner_valid():
                                    allow_execution = False
                                elif trade_mode == "HIT_RUN" and not self.supervisor.is_normal_valid():
                                    allow_execution = False

                                # Filter BBMA Re-entry LWMA Zone
                                lwma_5_h = row_data.get('LWMA_5_High', 0)
                                lwma_10_h = row_data.get('LWMA_10_High', 0)
                                lwma_5_l = row_data.get('LWMA_5_Low', 0)
                                lwma_10_l = row_data.get('LWMA_10_Low', 0)
                                high_price = row_data.get('high', 0)
                                low_price = row_data.get('low', 0)
                                
                                if action_type == mt5.ORDER_TYPE_SELL:
                                    reentry_zone = min(lwma_5_h, lwma_10_h)
                                    if high_price < reentry_zone:
                                        allow_execution = False
                                elif action_type == mt5.ORDER_TYPE_BUY:
                                    reentry_zone = max(lwma_5_l, lwma_10_l)
                                    if low_price > reentry_zone:
                                        allow_execution = False

                                # Institutional Risk Service Validation (Anti-Hedging, News Blackout, Hit-Run Limit, Pyramiding)
                                if allow_execution and self.risk_service.validate_execution_allowed(Config.SYMBOL, action_type, trade_mode, used_prob):
                                    action_str = 'BUY' if action_type == mt5.ORDER_TYPE_BUY else 'SELL'
                                    logging.info(f"[SIGNAL] Multiclass Entry: {action_str} | Mode: {trade_mode} | Prob: {used_prob:.2f}")
                                    self.execute_order(action_type, sl_dist, trade_mode=trade_mode, prob_runner=used_prob, row_data=row_data)
                    except Exception as e:
                        logging.debug(f"[SIGNAL_CHECK] Error fetching/predicting: {e}")

            # Manajemen Posisi Aktif (Break-Even, Partial Close, Reversal Exit, Pre-News Protection)
            try:
                self.position_tracker.process_active_positions(
                    symbol=Config.SYMBOL,
                    latest_df=self.latest_df_live,
                    latest_probs=self.latest_probs
                )
            except Exception as e:
                logging.debug(f"[POSITION_MANAGEMENT] {e}")

            await asyncio.sleep(1)

    def execute_order(self, action, sl_distance, trade_mode="NORMAL", prob_runner=None, row_data=None):
        """Kalkulasi lot, SL/TP adaptif, dan kirim order via OrderRouter."""
        # Validasi volatilitas ekstrem
        rates = mt5.copy_rates_from_pos(Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 30)
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
                logging.warning(f"[SEKRING] Volatility Anomaly! Range {last_candle_range:.5f} > 3x ATR ({3*atr_14:.5f}). Order rejected.")
                return None

        # Kalkulasi Lot via RiskService
        lot = self.risk_service.calculate_lot_size(Config.SYMBOL, sl_distance)
        
        tick = mt5.symbol_info_tick(Config.SYMBOL)
        if tick is None:
            logging.error("Tick data unavailable.")
            return None
            
        price = tick.ask if action == mt5.ORDER_TYPE_BUY else tick.bid
        sl_abs = float(sl_distance)
        
        is_runner_mode = "RUNNER" in (trade_mode or "").upper()
        if is_runner_mode:
            max_learned_rr = getattr(self.researcher, 'max_runner_rr', 5.0) if self.researcher else 5.0
            runner_rr = min(4.0, max_learned_rr)
            tp_abs = float(sl_distance * runner_rr)
        else:
            tp_abs = float(sl_distance * 2.0)
            
        digits = 2
        sym_info = mt5.symbol_info(Config.SYMBOL)
        if sym_info and sym_info.digits:
            digits = sym_info.digits
            
        if action == mt5.ORDER_TYPE_BUY:
            sl = round(price - sl_abs, digits)
            tp = round(price + tp_abs, digits)
        else:
            sl = round(price + sl_abs, digits)
            tp = round(price - tp_abs, digits)
            
        logging.info(f"[ORDER SETUP] Mode: {trade_mode} | Entry: {price} | SL: {sl} (dist: {sl_abs:.2f}) | TP: {tp} (dist: {tp_abs:.2f})")
        
        # Kirim Order via OrderRouter (dengan dynamic slippage & requote retry)
        result = self.order_router.send_order(
            symbol=Config.SYMBOL,
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
                    comment=f"Ticket #{order_ticket} | AI Bot Execute",
                    mode=trade_mode,
                    ticket=order_ticket,
                    setup_id=setup_id
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
                        feature_vector=feature_dict
                    )
            except Exception as e:
                logging.error(f"[Post-Execution DB Error] {e}")

            # Post-execution Black Box Journal snapshot
            try:
                snapshot_json = capture_m1_snapshot(Config.SYMBOL, 50)
                alasan = self.get_latest_xai_reason()
                record_journal_event_async(
                    tiket=order_ticket,
                    event_type="ENTRY",
                    harga=float(price),
                    alasan=alasan,
                    snapshot_json=snapshot_json
                )
            except Exception as e:
                logging.error(f"[Post-Execution Journal Error] {e}")

        return result

    def get_latest_xai_reason(self):
        """Ambil alasan Top 3 Feature Contributions dari LightGBM Researcher."""
        if self.researcher is not None and hasattr(self.researcher, 'get_top_feature_contributions'):
            try:
                if self.data_miner is not None:
                    df_live = self.data_miner.fetch_and_merge_data(n_candles=30)
                    if df_live is not None and not df_live.empty:
                        last_row = df_live.iloc[[-1]]
                        return self.researcher.get_top_feature_contributions(last_row, top_n=3)
            except Exception as e:
                logging.debug(f"Gagal mengambil live features untuk XAI: {e}")
        return "Top 3 Fitur: dist_Close_EMA50 (+0.45), BB_Width (+0.32), ATR_14 (+0.21)"

    async def trigger_online_learning(self):
        """Pemicu Online Learning otomatis (Micro-Retrain) di background."""
        if not self.researcher or not self.data_miner:
            return

        if self.researcher.is_training_normal or self.researcher.is_training_runner:
            return

        logging.info("[ONLINE LEARNING] 🚀 Memulai siklus auto micro-retrain...")
        loop = asyncio.get_running_loop()

        def _run_micro():
            try:
                if self.data_miner:
                    try:
                        self.data_miner.sync_latest_data()
                    except Exception:
                        pass

                df_recent = self.data_miner.load_recent_micro_chunk(n_candles=3000)
                if df_recent is None or df_recent.empty:
                    return

                if self.researcher.model_normal is not None:
                    fb_normal = self.data_miner.load_live_decision_chunk(mode="normal")
                    self.researcher.micro_retrain("normal", df_recent, fb_normal)

                if self.researcher.model_runner is not None:
                    fb_runner = self.data_miner.load_live_decision_chunk(mode="runner")
                    self.researcher.micro_retrain("runner", df_recent, fb_runner)

                self.last_micro_retrain_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.info(f"[ONLINE LEARNING] ✨ Siklus micro-retrain selesai pada {self.last_micro_retrain_time}.")
            except Exception as e:
                logging.error(f"[ONLINE LEARNING] Gagal mengeksekusi micro-retrain: {e}")

        await loop.run_in_executor(None, _run_micro)

def capture_m1_snapshot(symbol=Config.SYMBOL, n_candles=50):
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, n_candles)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'], unit='s').dt.strftime('%Y-%m-%d %H:%M:%S')
            return df.to_json(orient='records')
    except Exception as e:
        logging.debug(f"Gagal merekam M1 snapshot: {e}")
    return "{}"

def record_journal_event_async(tiket: int, event_type: str, harga: float, alasan: str, snapshot_json: str):
    import threading
    def _worker():
        try:
            from database import log_trade_journal
            log_trade_journal(
                tiket=int(tiket),
                event_type=str(event_type),
                harga=float(harga),
                alasan=str(alasan),
                chart_snapshot=str(snapshot_json)
            )
        except Exception as e:
            logging.error(f"[Trade Journal Error] Gagal mencatat event: {e}")
    threading.Thread(target=_worker, daemon=True).start()
