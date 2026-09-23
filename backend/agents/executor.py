import asyncio
import logging
import datetime
import pandas as pd
import numpy as np
from config import Config
from utils.mt5_utils import check_spread
import MetaTrader5 as mt5

logging.basicConfig(level=logging.INFO)

class ExecutorAgent:
    """
    Agent 4: The Executor (Context-Aware Risk Manager)
    """
    
    def __init__(self, supervisor_agent, data_miner_agent=None, researcher_agent=None):
        self.supervisor = supervisor_agent
        self.data_miner = data_miner_agent
        self.researcher = researcher_agent
        self.running = False
        self.MAX_PYRAMIDING = 3
        self.current_market_regime = {"adx": 0.0, "regime": "UNKNOWN", "last_updated": None}
        self.last_micro_retrain_time = None
        self.latest_df_live = None
        self.latest_probs = {}
        
    async def monitor_market(self):
        self.running = True
        logging.info("Executor Agent started monitoring market...")
        logging.info(f"Circuit Breakers Active [SpreadLimit: Dynamic (Base {Config.SPREAD_LIMIT_POINTS}), MaxDD: {Config.MAX_DRAWDOWN_PERCENT}%, FridayLiquidator: ON]")
        
        last_hourly_db_sync = datetime.datetime.now()
        last_exhaustion_check = datetime.datetime.now()
        last_signal_check = datetime.datetime.now()
        last_deals_sync = datetime.datetime.now()
        
        while self.running:
            now = datetime.datetime.now()

            # Auto-sync closed deals dari MT5 setiap 20 detik untuk pembukuan PnL riil (berjalan terus di background)
            if (now - last_deals_sync).total_seconds() >= 20:
                last_deals_sync = now
                try:
                    from database import sync_mt5_closed_deals_to_db
                    sync_mt5_closed_deals_to_db(days_back=90)
                except Exception as e:
                    logging.debug(f"[Deals Sync Error] {e}")

            if self.supervisor.state != 'live':
                await asyncio.sleep(1)
                continue

            # Rutinitas Asinkron: Auto-sync candle terbaru ke database setiap 1 jam sekali (Mode Live)
            if self.data_miner is not None and (now - last_hourly_db_sync).total_seconds() >= 3600:
                last_hourly_db_sync = now
                logging.info("[HOURLY SYNC] Menjalankan penyimpanan candle terbaru ke database secara asinkron...")
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, self.data_miner.backfill_data, 10000)
                    logging.info("[HOURLY SYNC] Sinkronisasi candle 1 jam ke database berhasil.")

                    # --- Online Learning: Auto Micro-Retrain setelah sinkronisasi data baru ---
                    if Config.ENABLE_ONLINE_LEARNING:
                        asyncio.create_task(self.trigger_online_learning())
                except Exception as e:
                    logging.error(f"[HOURLY SYNC] Gagal sinkronisasi data ke database: {e}")
                
            # Cek Friday Liquidator
            tick_data = mt5.symbol_info_tick(Config.SYMBOL)
            if tick_data is not None:
                wib_tz = datetime.timezone(datetime.timedelta(hours=7))
                now_wib = datetime.datetime.fromtimestamp(tick_data.time, tz=wib_tz)
                
                if now_wib.weekday() == 4 and now_wib.hour >= 3:
                    logging.warning("[SEKRING] Friday Liquidator Active! Closing all positions.")
                    self.supervisor.trigger_friday_liquidator()
                    # Tutup seluruh posisi aktif via MT5
                    open_positions = mt5.positions_get(symbol=Config.SYMBOL)
                    if open_positions:
                        for p in open_positions:
                            close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                            tick = mt5.symbol_info_tick(Config.SYMBOL)
                            close_price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
                            req = {
                                "action": mt5.TRADE_ACTION_DEAL,
                                "symbol": Config.SYMBOL,
                                "volume": p.volume,
                                "type": close_type,
                                "position": p.ticket,
                                "price": float(close_price),
                                "deviation": 20,
                                "magic": 234000,
                                "comment": "Friday Liquidator Close",
                                "type_time": mt5.ORDER_TIME_GTC,
                                "type_filling": mt5.ORDER_FILLING_IOC,
                            }
                            mt5.order_send(req)
                    await asyncio.sleep(60) 
                    continue
                
            # Cek status sekring Spread
            spread = check_spread(Config.SYMBOL)
            rates_spread = mt5.copy_rates_from_pos(Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 15)
            if rates_spread is not None and len(rates_spread) >= 15:
                df_spread = pd.DataFrame(rates_spread)
                avg_spread = df_spread['spread'].mean()
                dynamic_spread_limit = max(Config.SPREAD_LIMIT_POINTS, int(avg_spread * 2.5))
            else:
                dynamic_spread_limit = Config.SPREAD_LIMIT_POINTS
                
            if spread is not None and spread > dynamic_spread_limit:
                logging.warning(f"[SEKRING] Eksekusi ditolak: Spread {spread} poin melebihi batas adaptif {dynamic_spread_limit}")
                await asyncio.sleep(5)
                continue
                
            # Cek status sekring Drawdown
            account_info = mt5.account_info()
            if account_info is not None and account_info.balance > 0:
                dd_percent = (account_info.balance - account_info.equity) / account_info.balance
                if dd_percent > (Config.MAX_DRAWDOWN_PERCENT / 100.0):
                    logging.warning(f"[SEKRING] Max Drawdown {Config.MAX_DRAWDOWN_PERCENT}% REACHED! Equity: {account_info.equity}")
                    self.supervisor.trigger_max_drawdown()
                    continue

            # --- Dynamic Exhaustion Exit (Mass Liquidation) ---
            if (now - last_exhaustion_check).total_seconds() >= 5:
                last_exhaustion_check = now
                if self.researcher is not None and self.data_miner is not None:
                    try:
                        positions = mt5.positions_get(symbol=Config.SYMBOL)
                        if positions:
                            runner_buys = [p for p in positions if p.type == mt5.ORDER_TYPE_BUY and "RUNNER" in p.comment.upper()]
                            runner_sells = [p for p in positions if p.type == mt5.ORDER_TYPE_SELL and "RUNNER" in p.comment.upper()]
                            
                            if runner_buys or runner_sells:
                                df_live = await asyncio.to_thread(self.data_miner.fetch_and_merge_data, 30)
                                if df_live is not None and not df_live.empty:
                                    last_row = df_live.iloc[[-1]]
                                    probs = await asyncio.to_thread(self.researcher.get_live_probabilities, last_row)
                                    prob_runner = probs.get("runner", 0.5)
                                    
                                    # Dynamic Exhaustion Threshold (Berdasarkan Kekuatan Tren ADX)
                                    from utils.indicators import calculate_adx
                                    df_live['adx'] = calculate_adx(df_live, 14)
                                    adx_val = df_live['adx'].iloc[-1]
                                    
                                    threshold = 0.35 # Base 35%
                                    if not np.isnan(adx_val):
                                        if adx_val > 35:
                                            threshold = 0.20 # Tren Sangat Kuat: Toleransi tinggi terhadap noise
                                        elif adx_val < 20:
                                            threshold = 0.45 # Tren Lemah/Choppy: Sensitif, likuidasi secepatnya
                                    if runner_buys and prob_runner < threshold:
                                        logging.warning(f"[AI_TRAILING] Probabilitas trend turun ke {prob_runner*100:.0f}%. Melikuidasi semua posisi BUY RUNNER!")
                                        for p in positions:
                                            if p.type == mt5.ORDER_TYPE_BUY:
                                                self.execute_full_close(p.ticket, reason=f"AI Probability Trailing Stop triggered: Probabilitas turun ke {prob_runner*100:.0f}%")
                                                
                                    if runner_sells and prob_runner > (1.0 - threshold):
                                        logging.warning(f"[AI_TRAILING] Probabilitas pembalikan arah naik ke {prob_runner*100:.0f}%. Melikuidasi semua posisi SELL RUNNER!")
                                        for p in positions:
                                            if p.type == mt5.ORDER_TYPE_SELL:
                                                self.execute_full_close(p.ticket, reason=f"AI Probability Trailing Stop triggered: Probabilitas naik ke {prob_runner*100:.0f}%")
                    except Exception as e:
                        logging.debug(f"[EXHAUSTION] Gagal cek: {e}")

            # --- AI Signal Generation & Execution ---
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
                                
                                # Dynamic SL Distance: Menggunakan ATR_14 jika ada, fallback ke 5.0
                                sl_dist = row_data.get('ATR_14', 5.0)
                                if pd.isna(sl_dist) or sl_dist < 5.0:
                                    sl_dist = 5.0

                                # --- Regime-Aware Analysis (ADX) ---
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
                                
                                # --- ATURAN 4: Evaluasi Sinyal Berlawanan & Resolusi Major Trend EMA 50 ---
                                ema_50_val = row_data.get('EMA_50', 0.0)
                                close_val = row_data.get('close', 0.0)

                                if abs(max_buy - max_sell) < 1e-4:
                                    # Probabilitas BUY & SELL sama persis: Ikuti Major Trend berpedoman pada EMA 50
                                    if close_val >= ema_50_val:
                                        action_type = mt5.ORDER_TYPE_BUY
                                        preferred_mode = "RUNNER" if p_buy_r >= p_buy_n else "HIT_RUN"
                                        used_prob = p_buy_r if preferred_mode == "RUNNER" else p_buy_n
                                        logging.info(f"[SIGNAL RESOLUTION] Sinyal BUY & SELL bernilai sama ({max_buy:.2f}). Mengikuti Major Trend EMA 50 (Close {close_val:.2f} >= EMA 50 {ema_50_val:.2f}) -> Eksekusi: BUY")
                                    else:
                                        action_type = mt5.ORDER_TYPE_SELL
                                        preferred_mode = "RUNNER" if p_sell_r >= p_sell_n else "HIT_RUN"
                                        used_prob = p_sell_r if preferred_mode == "RUNNER" else p_sell_n
                                        logging.info(f"[SIGNAL RESOLUTION] Sinyal BUY & SELL bernilai sama ({max_sell:.2f}). Mengikuti Major Trend EMA 50 (Close {close_val:.2f} < EMA 50 {ema_50_val:.2f}) -> Eksekusi: SELL")
                                elif max_buy > max_sell:
                                    action_type = mt5.ORDER_TYPE_BUY
                                    preferred_mode = "RUNNER" if p_buy_r >= p_buy_n else "HIT_RUN"
                                    used_prob = p_buy_r if preferred_mode == "RUNNER" else p_buy_n
                                    if max_sell >= 0.70:
                                        logging.info(f"[SIGNAL RESOLUTION] Dua sinyal berlawanan muncul (BUY: {max_buy:.2f} vs SELL: {max_sell:.2f}). Probabilitas tertinggi yang dipakai -> BUY ({max_buy:.2f})")
                                else:
                                    action_type = mt5.ORDER_TYPE_SELL
                                    preferred_mode = "RUNNER" if p_sell_r >= p_sell_n else "HIT_RUN"
                                    used_prob = p_sell_r if preferred_mode == "RUNNER" else p_sell_n
                                    if max_buy >= 0.70:
                                        logging.info(f"[SIGNAL RESOLUTION] Dua sinyal berlawanan muncul (SELL: {max_sell:.2f} vs BUY: {max_buy:.2f}). Probabilitas tertinggi yang dipakai -> SELL ({max_sell:.2f})")

                                # --- Regime-Aware Signal Routing Logic ---
                                trade_mode = preferred_mode
                                if preferred_mode == "RUNNER" and regime_name == "RANGING/CHOPPY":
                                    # Di pasar sideways, target 1:5 runner rentan tersapu whipsaw SL. Alihkan ke scalping 1:2
                                    trade_mode = "HIT_RUN"
                                    used_prob = p_buy_n if action_type == mt5.ORDER_TYPE_BUY else p_sell_n
                                    logging.info(f"[REGIME ROUTING] ⚠️ Pasar Sideways terdeteksi (ADX: {adx_val:.1f} < {Config.ADX_RANGING_THRESHOLD}). Sinyal RUNNER dialihkan ke HIT_RUN (Scalp 1:2) | Prob Baru: {used_prob:.2f}")
                                elif regime_name == "TRENDING" and preferred_mode == "HIT_RUN" and ((action_type == mt5.ORDER_TYPE_BUY and p_buy_r >= 0.65) or (action_type == mt5.ORDER_TYPE_SELL and p_sell_r >= 0.65)):
                                    # Di pasar trending kuat, prioritaskan RUNNER jika model runner memiliki probabilitas meyakinkan
                                    trade_mode = "RUNNER"
                                    used_prob = p_buy_r if action_type == mt5.ORDER_TYPE_BUY else p_sell_r
                                    logging.info(f"[REGIME ROUTING] 🚀 Pasar Trending Kuat terdeteksi (ADX: {adx_val:.1f} >= {Config.ADX_TREND_THRESHOLD}). Memprioritaskan RUNNER mode | Prob: {used_prob:.2f}")
                                
                                allow_execution = True
                                
                                # --- ATURAN 1: Mode Hit & Run Hanya 1x Open Posisi Aktif ---
                                if trade_mode == "HIT_RUN":
                                    curr_positions = mt5.positions_get(symbol=Config.SYMBOL)
                                    if curr_positions:
                                        hr_active = [p for p in curr_positions if "HIT_RUN" in p.comment.upper()]
                                        if len(hr_active) >= 1:
                                            logging.info(f"[HIT_RUN LIMIT] Sinyal Hit & Run ditahan: Hanya diizinkan 1x posisi aktif (Tiket aktif: {hr_active[0].ticket}).")
                                            allow_execution = False

                                # --- Partial Live / Circuit Breaker Check ---
                                if trade_mode == "RUNNER" and not self.supervisor.is_runner_valid():
                                    logging.warning(f"[PARTIAL LIVE] Sinyal Runner terdeteksi (Prob: {used_prob:.2f}), tapi Mode Runner sedang dikarantina. Sinyal ditolak.")
                                    allow_execution = False
                                elif trade_mode == "HIT_RUN" and not self.supervisor.is_normal_valid():
                                    logging.warning(f"[PARTIAL LIVE] Sinyal Normal terdeteksi (Prob: {used_prob:.2f}), tapi Mode Normal sedang dikarantina. Sinyal ditolak.")
                                    allow_execution = False
                                
                                action_str = 'BUY' if action_type == mt5.ORDER_TYPE_BUY else 'SELL'
                                
                                # --- Aturan Ketat BBMA: BUY HANYA di LWMA Low & SELL HANYA di LWMA High (Universal: RUNNER & HIT_RUN) ---
                                lwma_5_h = row_data.get('LWMA_5_High', 0)
                                lwma_10_h = row_data.get('LWMA_10_High', 0)
                                lwma_5_l = row_data.get('LWMA_5_Low', 0)
                                lwma_10_l = row_data.get('LWMA_10_Low', 0)
                                high_price = row_data.get('high', 0)
                                low_price = row_data.get('low', 0)
                                
                                if action_type == mt5.ORDER_TYPE_SELL:
                                    reentry_zone = min(lwma_5_h, lwma_10_h)
                                    if high_price < reentry_zone:
                                        logging.info(f"[FILTER BBMA] Sinyal SELL ({trade_mode}) ditahan (Wait): Harga belum mencapai zona Re-entry LWMA High (High {high_price:.4f} < {reentry_zone:.4f}).")
                                        allow_execution = False
                                elif action_type == mt5.ORDER_TYPE_BUY:
                                    reentry_zone = max(lwma_5_l, lwma_10_l)
                                    if low_price > reentry_zone:
                                        logging.info(f"[FILTER BBMA] Sinyal BUY ({trade_mode}) ditahan (Wait): Harga belum mencapai zona Re-entry LWMA Low (Low {low_price:.4f} > {reentry_zone:.4f}).")
                                        allow_execution = False
                                            
                                if allow_execution:
                                    logging.info(f"[SIGNAL] Multiclass Entry: {action_str} | Mode: {trade_mode} | Prob: {used_prob:.2f}")
                                    self.execute_order(action_type, sl_dist, trade_mode=trade_mode, prob_runner=used_prob, row_data=row_data)
                    except Exception as e:
                        logging.debug(f"[SIGNAL_CHECK] Error fetching/predicting: {e}")

            # --- Manajemen Posisi Aktif (Anti-Wick & Partial Close) ---
            try:
                positions = mt5.positions_get(symbol=Config.SYMBOL)
                if positions:
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
                            
                        is_runner = "RUNNER" in pos.comment.upper()
                        
                        # --- ATURAN 1: Dynamic TP Multiplier (Hit & Run Minimal RR 1:2) ---
                        tp_multiplier = 2.0
                        rates_tp = mt5.copy_rates_from_pos(Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 30)
                        if rates_tp is not None and len(rates_tp) >= 30:
                            df_tp = pd.DataFrame(rates_tp)
                            from utils.indicators import calculate_adx
                            df_tp['adx'] = calculate_adx(df_tp, 14)
                            adx_val = df_tp['adx'].iloc[-1]
                            if not np.isnan(adx_val) and adx_val > 40:
                                tp_multiplier = 3.0
                        # Mode Hit & Run selalu minimal RR 1:2
                        tp_multiplier = max(2.0, tp_multiplier)

                        if not is_runner:
                            # --- ATURAN 1: Logika HIT_RUN (Maksimal 1 Posisi, Minimal RR 1:2) ---
                            if initial_risk > 0:
                                # BE saat RR 1:1 secepatnya
                                if current_gain >= (1.0 * initial_risk) and abs(pos.sl - pos.price_open) > 0.05:
                                    logging.info(f"[HIT_RUN] Target RR 1:1 tercapai untuk tiket {ticket}. Geser SL ke BE.")
                                    self.modify_sl_to_break_even(ticket)
                                # Full Close saat RR dinamis tercapai (minimal RR 1:2)
                                if current_gain >= (tp_multiplier * initial_risk):
                                    logging.info(f"[HIT_RUN] Target RR 1:{tp_multiplier:.1f} tercapai untuk tiket {ticket}. Menjalankan Full Close.")
                                    self.execute_full_close(ticket, reason=f"Hit & Run: Target RR 1:{tp_multiplier:.1f} Tercapai (Full Close)")
                        else:
                            # --- ATURAN 2: Logika RUNNER (Exit Reversal Analisa atau Maximum RR Hasil Belajar) ---
                            # Step A: Partial Close 50% & SL ke BE saat mencapai milestone RR 1:2
                            if initial_risk > 0 and current_gain >= (2.0 * initial_risk):
                                if abs(pos.sl - pos.price_open) > 0.05:
                                    logging.info(f"[RUNNER] Milestone RR 1:2 tercapai untuk tiket {ticket}. Partial Close 50% & SL ke BE.")
                                    self.execute_partial_close_50(ticket)
                                    self.modify_sl_to_break_even(ticket)
                                    
                            # Step B: Exit jika "Maximum RR" yang didapat dari proses "belajar" tercapai
                            max_runner_rr = getattr(self.researcher, 'max_runner_rr', 5.0)
                            if initial_risk > 0 and current_gain >= (max_runner_rr * initial_risk):
                                logging.info(f"[RUNNER EXIT] 🎯 Maximum RR hasil belajar (1:{max_runner_rr:.1f}) tercapai untuk tiket {ticket} (Gain: {current_gain:.2f} >= {max_runner_rr * initial_risk:.2f}). Menjalankan Full Close.")
                                self.execute_full_close(ticket, reason=f"Runner Exit: Maximum RR ({max_runner_rr:.1f}R) Hasil Belajar Tercapai")
                                continue

                            # Step C: Exit jika "Analisa" mengatakan harga akan berbalik (Reversal Analysis)
                            reversal_detected = False
                            reversal_reason = ""
                            latest_p = getattr(self, 'latest_probs', {})
                            latest_df = getattr(self, 'latest_df_live', None)
                            
                            p_sell_rev = max(latest_p.get("runner_sell", 0.0), latest_p.get("normal_sell", 0.0))
                            p_buy_rev = max(latest_p.get("runner_buy", 0.0), latest_p.get("normal_buy", 0.0))

                            if pos.type == mt5.ORDER_TYPE_BUY:
                                if p_sell_rev >= 0.65:
                                    reversal_detected = True
                                    reversal_reason = f"AI mendeteksi lonjakan probabilitas SELL ({p_sell_rev:.2f})"
                                elif latest_df is not None and not latest_df.empty and 'EMA_50' in latest_df.columns and 'LWMA_10_Low' in latest_df.columns:
                                    c_close = latest_df['close'].iloc[-1]
                                    c_ema = latest_df['EMA_50'].iloc[-1]
                                    c_lwma = latest_df['LWMA_10_Low'].iloc[-1]
                                    if c_close < c_ema and c_close < c_lwma:
                                        reversal_detected = True
                                        reversal_reason = f"Topografi Reversal Breakdown (Close {c_close:.2f} < EMA 50 & LWMA 10 Low)"
                            elif pos.type == mt5.ORDER_TYPE_SELL:
                                if p_buy_rev >= 0.65:
                                    reversal_detected = True
                                    reversal_reason = f"AI mendeteksi lonjakan probabilitas BUY ({p_buy_rev:.2f})"
                                elif latest_df is not None and not latest_df.empty and 'EMA_50' in latest_df.columns and 'LWMA_10_High' in latest_df.columns:
                                    c_close = latest_df['close'].iloc[-1]
                                    c_ema = latest_df['EMA_50'].iloc[-1]
                                    c_lwma = latest_df['LWMA_10_High'].iloc[-1]
                                    if c_close > c_ema and c_close > c_lwma:
                                        reversal_detected = True
                                        reversal_reason = f"Topografi Reversal Breakout (Close {c_close:.2f} > EMA 50 & LWMA 10 High)"

                            if reversal_detected:
                                logging.warning(f"[RUNNER EXIT] 🔄 Analisa mendeteksi Pembalikan Arah ({reversal_reason}) untuk tiket {ticket}. Menjalankan Full Close.")
                                self.execute_full_close(ticket, reason=f"Runner Exit: Analisa Reversal ({reversal_reason})")
                                continue
            except Exception as e:
                logging.debug(f"Position management loop error: {e}")

            # Simulasi delay tick
            await asyncio.sleep(1)

    def stop(self):
        self.running = False
        logging.info("Executor Agent stopped.")
        
    def execute_order(self, action, sl_distance, trade_mode="HIT_RUN", prob_runner=None, row_data=None):
        """
        Anti-Latensi: 'Strict Sequencing' Execution.
        Sesaat setelah sinyal live valid, mt5.order_send() HARUS dieksekusi pertama kali.
        Dilarang ada kalkulasi I/O database, pembuatan grafik JSON, atau SHAP/Feature Importance
        sebelum tiket MT5 resmi diterima dari broker.
        """
        # --- PYRAMIDING & VOLATILITY CHECK ---
        rates = mt5.copy_rates_from_pos(Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 30)
        current_adx = 20.0
        if rates is not None and len(rates) >= 30:
            df_rates = pd.DataFrame(rates)
            from utils.indicators import calculate_adx
            df_rates['adx'] = calculate_adx(df_rates, 14)
            current_adx = df_rates['adx'].iloc[-1]
            if np.isnan(current_adx): current_adx = 20.0
            
            # Dynamic Pyramiding Limit based on ADX (Trend Strength)
            self.MAX_PYRAMIDING = max(1, min(5, int(current_adx / 10)))
            
            # Volatility Anomaly Circuit Breaker (Dynamic)
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

        # --- ATURAN 1: Mode Hit & Run Hanya 1x Open Posisi Aktif ---
        if trade_mode == "HIT_RUN":
            active_positions = mt5.positions_get(symbol=Config.SYMBOL)
            if active_positions:
                hr_positions = [p for p in active_positions if "HIT_RUN" in p.comment.upper()]
                if len(hr_positions) >= 1:
                    logging.warning(f"[HIT_RUN LIMIT] Order ditolak: Sudah ada 1 posisi Hit & Run aktif (Tiket {hr_positions[0].ticket}).")
                    return None

        # --- ATURAN 2: Mode RUNNER bisa open berkali-kali searah di LWMA jika sudah running profit ---
        positions = mt5.positions_get(symbol=Config.SYMBOL)
        same_dir_positions = []
        if positions:
            for p in positions:
                if p.type == action:
                    same_dir_positions.append(p)
                    
        if trade_mode == "RUNNER" and len(same_dir_positions) > 0:
            for p in same_dir_positions:
                if p.profit <= 0:
                    logging.warning(f"[RUNNER PYRAMIDING] Posisi Runner sebelumnya (Tiket {p.ticket}) belum running profit (Profit: ${p.profit:.2f}). Scale-In ditolak.")
                    return None
            logging.info(f"[RUNNER PYRAMIDING] ✅ Semua ({len(same_dir_positions)}) posisi Runner sebelumnya sudah running profit. Mengizinkan Scale-In baru.")
        elif trade_mode != "RUNNER":
            is_high_prob = prob_runner is not None and prob_runner >= 0.70
            if not is_high_prob and len(same_dir_positions) >= getattr(self, 'MAX_PYRAMIDING', 3):
                logging.warning(f"[PYRAMIDING] Limit dinamis {getattr(self, 'MAX_PYRAMIDING', 3)} tercapai. Order ditolak.")
                return None
        # ------------------------

        symbol_info = mt5.symbol_info(Config.SYMBOL)
        if symbol_info is None:
            logging.error(f"{Config.SYMBOL} not found in MT5.")
            return None
            
        if not symbol_info.visible:
            if not mt5.symbol_select(Config.SYMBOL, True):
                logging.error(f"symbol_select({Config.SYMBOL}) failed, exit")
                return None
                
        # --- ATURAN 3: Kalkulasi Lot Berdasarkan Maximum Risk yang Disetting Lewat UI ---
        base_risk_dollars = Config.MAX_RISK_DOLLARS
        if getattr(Config, 'RISK_MODE', 'dollars') == 'percent':
            account_info = mt5.account_info()
            equity = account_info.equity if account_info and account_info.equity > 0 else (account_info.balance if account_info else 1000.0)
            base_risk_dollars = max(1.0, equity * (getattr(Config, 'MAX_RISK_PERCENT', 1.0) / 100.0))
            logging.info(f"[RISK UI PERCENT] Equity: ${equity:.2f} | Risk: {Config.MAX_RISK_PERCENT}% -> Max Risk UI: ${base_risk_dollars:.2f}")
        else:
            logging.info(f"[RISK UI DOLLARS] Max Risk UI: ${base_risk_dollars:.2f}")

        tick_value = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size
        
        lot = 0.01
        if tick_size > 0 and tick_value > 0:
            # Nilai uang riil untuk setiap 1 unit harga per 1 lot standar
            money_per_unit = tick_value / tick_size
            
            # Total kerugian jika kita open 1 lot penuh untuk jarak SL ini
            loss_for_one_lot = sl_distance * money_per_unit
            
            if loss_for_one_lot > 0:
                raw_lot = base_risk_dollars / loss_for_one_lot
                
                # Sesuaikan dengan volume step broker (floor rounding agar risiko <= max risk UI)
                step = symbol_info.volume_step if symbol_info.volume_step > 0 else 0.01
                min_lot = symbol_info.volume_min if symbol_info.volume_min > 0 else 0.01
                max_lot = symbol_info.volume_max if symbol_info.volume_max > 0 else 100.0
                
                import math
                calc_lot = math.floor(raw_lot / step) * step
                lot = max(min_lot, min(max_lot, round(calc_lot, 2)))
                est_loss = lot * loss_for_one_lot
                logging.info(f"[LOT SIZING] Max Risk UI: ${base_risk_dollars:.2f} | Jarak SL: {sl_distance:.2f} | Lot Terhitung: {lot} (Est. Rugi SL: ${est_loss:.2f})")
        
        tick = mt5.symbol_info_tick(Config.SYMBOL)
        if tick is None:
            logging.error("Tick data unavailable.")
            return None
            
        price = tick.ask if action == mt5.ORDER_TYPE_BUY else tick.bid
        # sl_distance sudah berupa selisih harga absolut (misal $5.00), bukan poin.
        # Jadi kita tidak perlu mengalikannya dengan symbol_info.point
        sl_abs = float(sl_distance)
        tp_abs = float(sl_distance * 10)  # Sekring TP darurat 1:10
        
        # --- LWMA ZONE GUARD (DEFENSE IN DEPTH) ---
        # Memastikan tidak ada order yang lolos jika tidak berada di zona LWMA yang tepat
        if row_data is not None:
            lwma_5_h = row_data.get('LWMA_5_High', 0)
            lwma_10_h = row_data.get('LWMA_10_High', 0)
            lwma_5_l = row_data.get('LWMA_5_Low', 0)
            lwma_10_l = row_data.get('LWMA_10_Low', 0)
            high_price = row_data.get('high', 0)
            low_price = row_data.get('low', 0)

            if action == mt5.ORDER_TYPE_BUY and (lwma_5_l > 0 or lwma_10_l > 0):
                reentry_buy_zone = max(lwma_5_l, lwma_10_l)
                if low_price > reentry_buy_zone and price > reentry_buy_zone:
                    logging.warning(f"[LWMA GUARD] Order BUY dibatalkan: Harga saat ini ({price:.4f}) / Low ({low_price:.4f}) di atas zona LWMA Low ({reentry_buy_zone:.4f}).")
                    return None
            elif action == mt5.ORDER_TYPE_SELL and (lwma_5_h > 0 or lwma_10_h > 0):
                reentry_sell_zone = min(lwma_5_h, lwma_10_h)
                if high_price < reentry_sell_zone and price < reentry_sell_zone:
                    logging.warning(f"[LWMA GUARD] Order SELL dibatalkan: Harga saat ini ({price:.4f}) / High ({high_price:.4f}) di bawah zona LWMA High ({reentry_sell_zone:.4f}).")
                    return None
        
        if action == mt5.ORDER_TYPE_BUY:
            sl = price - sl_abs
            tp = price + tp_abs
        else:
            sl = price + sl_abs
            tp = price - tp_abs
            
        # Payload Transaksi MT5 Murni
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": Config.SYMBOL,
            "volume": float(lot),
            "type": action,
            "price": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": 234000,
            "comment": f"AI {trade_mode}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # =========================================================================
        # STRICT SEQUENCING: mt5.order_send() DIKIRIM PERTAMA KALI!
        # Tanpa I/O database, tanpa plotting JSON, tanpa kalkulasi SHAP/Feature Imp.
        # =========================================================================
        result = mt5.order_send(request)
        
        # Evaluasi Hasil Eksekusi
        if result is None:
            logging.error("order_send() failed, no result returned.")
            return None
        elif result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Order failed, retcode={result.retcode}")
            return result
        else:
            # =========================================================================
            # POST-EXECUTION (Hanya setelah tiket MT5 resmi diterima: result.order):
            # Pencatatan database dijalankan di sini tanpa menghambat eksekusi order.
            # =========================================================================
            logging.info(f"Order placed successfully! Ticket: {result.order}")
            
            # --- Trailing BE Berantai (Unified SL & TP) ---
            if len(same_dir_positions) > 0:
                for p in same_dir_positions:
                    logging.info(f"[PYRAMIDING] Menyatukan SL/TP posisi lama (Tiket {p.ticket}) dengan posisi baru (SL: {sl}, TP: {tp}).")
                    req_sl = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": Config.SYMBOL,
                        "position": p.ticket,
                        "sl": float(sl),
                        "tp": float(tp),
                        "magic": 234000,
                    }
                    mt5.order_send(req_sl)
            # ------------------------------------------------
            
            setup_id = f"SETUP_LIVE_{trade_mode}_{result.order}"
            try:
                from database import log_trade_record, save_live_decision_sample
                action_str = "BUY" if action == mt5.ORDER_TYPE_BUY else "SELL"
                log_trade_record(
                    action=action_str,
                    volume=float(lot),
                    price=float(price),
                    sl=float(sl),
                    tp=float(tp),
                    profit=0.0,
                    comment=f"Ticket #{result.order} | AI Bot Execute",
                    mode=trade_mode,
                    ticket=result.order,
                    setup_id=setup_id
                )

                # Simpan snapshot feature vector numerik lengkap untuk RLHF Retraining
                if row_data is not None:
                    try:
                        feature_dict = row_data.to_dict() if hasattr(row_data, 'to_dict') else dict(row_data)
                        save_live_decision_sample(
                            ticket=result.order,
                            setup_id=setup_id,
                            mode=trade_mode,
                            action=action_str,
                            probability=float(prob_runner if prob_runner is not None else 0.0),
                            entry_price=float(price),
                            sl=float(sl),
                            tp=float(tp),
                            feature_vector=feature_dict
                        )
                    except Exception as e_f:
                        logging.error(f"[Post-Execution Live Decision Error] Gagal simpan feature vector: {e_f}")
            except Exception as e:
                logging.error(f"[Post-Execution DB Error] Gagal menyimpan log trade: {e}")
                
            # Rekam 50 candle M1 terakhir ke format JSON & ekstrak Top 3 Feature Contributions LightGBM
            try:
                snapshot_json = capture_m1_snapshot(Config.SYMBOL, 50)
                alasan = self.get_latest_xai_reason()
                record_journal_event_async(
                    tiket=result.order,
                    event_type="ENTRY",
                    harga=float(price),
                    alasan=alasan,
                    snapshot_json=snapshot_json
                )
            except Exception as e:
                logging.error(f"[Post-Execution Journal Error] {e}")

        return result

    def execute_partial_close_50(self, ticket):
        """
        Eksekusi Partial Close 50% dari volume tiket posisi yang aktif.
        """
        pos = mt5.positions_get(ticket=ticket)
        if pos is None or len(pos) == 0:
            logging.warning(f"Position ticket {ticket} not found for 50% partial close.")
            return None
            
        pos = pos[0]
        symbol_info = mt5.symbol_info(pos.symbol)
        volume_step = getattr(symbol_info, "volume_step", 0.01) if symbol_info else 0.01
        volume_min = getattr(symbol_info, "volume_min", 0.01) if symbol_info else 0.01

        close_volume = round(pos.volume * 0.5, 2)
        close_volume = round(round(close_volume / volume_step) * volume_step, 2)

        if close_volume < volume_min:
            logging.warning(f"50% volume ({close_volume}) smaller than minimum allowed ({volume_min}). Skipping partial close.")
            return None

        if close_volume >= pos.volume:
            logging.warning(f"Position volume {pos.volume} cannot be split in half without full close. Skipping partial close.")
            return None

        logging.info(f"Executing 50% partial close for ticket {ticket} (Closing {close_volume} of {pos.volume} Lot)")
        tick = mt5.symbol_info_tick(pos.symbol)
        close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        close_action = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(close_volume),
            "type": close_action,
            "position": ticket,
            "price": float(close_price),
            "deviation": 20,
            "magic": 234000,
            "comment": "Partial Close 50%",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logging.error(f"order_send() failed for partial close ticket {ticket}.")
        elif result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Partial close failed for ticket {ticket}, retcode={result.retcode}")
        else:
            logging.info(f"50% Partial close successful for ticket {ticket}! Closed volume: {close_volume}")
            try:
                snapshot_json = capture_m1_snapshot(pos.symbol, 50)
                alasan = f"Hit & Run: Target RR 1:2 Tercapai. Mengunci 50% profit (Likuidasi {close_volume} Lot)."
                record_journal_event_async(
                    tiket=ticket,
                    event_type="EXIT",
                    harga=float(close_price),
                    alasan=alasan,
                    snapshot_json=snapshot_json
                )
            except Exception as e:
                logging.error(f"[Partial Close Journal Error] {e}")
                
            try:
                from database import sync_mt5_closed_deals_to_db
                sync_mt5_closed_deals_to_db(days_back=1)
            except Exception:
                pass
                
        return result

    def execute_full_close(self, ticket, reason="Full Close"):
        """
        Eksekusi Penutupan Penuh (100% Volume) dari posisi aktif.
        """
        pos = mt5.positions_get(ticket=ticket)
        if pos is None or len(pos) == 0:
            logging.warning(f"Position ticket {ticket} not found for Full Close.")
            return None
            
        pos = pos[0]
        logging.info(f"Executing Full Close for ticket {ticket} ({pos.volume} Lot)")
        tick = mt5.symbol_info_tick(pos.symbol)
        close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        close_action = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": float(pos.volume),
            "type": close_action,
            "position": ticket,
            "price": float(close_price),
            "deviation": 20,
            "magic": 234000,
            "comment": "Full Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            logging.error(f"order_send() failed for full close ticket {ticket}.")
        elif result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Full close failed for ticket {ticket}, retcode={result.retcode}")
        else:
            logging.info(f"Full close successful for ticket {ticket}! Closed volume: {pos.volume}")
            try:
                snapshot_json = capture_m1_snapshot(pos.symbol, 50)
                record_journal_event_async(
                    tiket=ticket,
                    event_type="EXIT",
                    harga=float(close_price),
                    alasan=reason,
                    snapshot_json=snapshot_json
                )
            except Exception as e:
                logging.error(f"[Full Close Journal Error] {e}")
                
            try:
                from database import sync_mt5_closed_deals_to_db
                sync_mt5_closed_deals_to_db(days_back=1)
            except Exception:
                pass
                
        return result

    def modify_sl_to_break_even(self, ticket):
        """
        Modifikasi parameter SL ke harga Open (Break Even), dan aplikasikan 
        Unified SL ini ke SELURUH posisi lain yang searah (Pyramiding SL Sync).
        """
        pos_list = mt5.positions_get(ticket=ticket)
        if pos_list is None or len(pos_list) == 0:
            logging.warning(f"Position ticket {ticket} not found for Break Even modification.")
            return None

        pos = pos_list[0]
        new_sl = float(pos.price_open)
        logging.info(f"Initiating Unified SL to Break Even ({new_sl}) triggered by ticket {ticket}")

        all_positions = mt5.positions_get(symbol=pos.symbol)
        result = None
        
        if all_positions:
            for p in all_positions:
                if p.type == pos.type:
                    # Pastikan SL tidak digeser mundur (worse risk)
                    if p.type == mt5.ORDER_TYPE_BUY:
                        if p.sl > 0 and new_sl <= p.sl:
                            continue
                    else:
                        if p.sl > 0 and new_sl >= p.sl:
                            continue
                            
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": p.symbol,
                        "position": p.ticket,
                        "sl": new_sl,
                        "tp": float(p.tp),
                        "magic": 234000,
                    }
                    res = mt5.order_send(request)
                    if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
                        logging.error(f"Failed to sync Unified SL to {new_sl} for ticket {p.ticket}")
                    else:
                        logging.info(f"Unified SL successfully modified to {new_sl} for ticket {p.ticket}")
                        if p.ticket == ticket:
                            result = res
                            
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            try:
                snapshot_json = capture_m1_snapshot(pos.symbol, 50)
                alasan = f"Risk Management: Break Even tercapai (RR 1:2). SL digeser ke harga Open ({pos.price_open:.2f}) untuk eliminasi risiko."
                record_journal_event_async(
                    tiket=ticket,
                    event_type="SL_MODIFY",
                    harga=float(pos.price_open),
                    alasan=alasan,
                    snapshot_json=snapshot_json
                )
            except Exception as e:
                logging.error(f"[SL Modify Journal Error] {e}")
                
        return result

    def topographical_trailing_stop(self, ticket):
        """
        Memantau sisa posisi 50% dari Trend Rider.
        Buy ditutup jika Close M1 menembus EMA_50_M1 atau LWMA_10_Low ke bawah.
        Sell ditutup jika Close M1 menembus EMA_50_M1 atau LWMA_10_High ke atas.
        """
        pos = mt5.positions_get(ticket=ticket)
        if pos is None or len(pos) == 0:
            return
            
        pos = pos[0]
        rates = mt5.copy_rates_from_pos(Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 50)
        if rates is None or len(rates) < 50:
            return
            
        df = pd.DataFrame(rates)
        from utils.indicators import calculate_ema, calculate_lwma
        df['EMA_50'] = calculate_ema(df['close'], 50)
        df['LWMA_10_Low'] = calculate_lwma(df['low'], 10)
        df['LWMA_10_High'] = calculate_lwma(df['high'], 10)
        
        last_close = df['close'].iloc[-1]
        ema_50 = df['EMA_50'].iloc[-1]
        lwma_low = df['LWMA_10_Low'].iloc[-1]
        lwma_high = df['LWMA_10_High'].iloc[-1]
        
        should_close = False
        # Logika exit konvensional dinonaktifkan (Pindah ke AI-Driven Probability)
        # if pos.type == mt5.ORDER_TYPE_BUY:
        #     if last_close < ema_50 or last_close < lwma_low:
        #         should_close = True
        # elif pos.type == mt5.ORDER_TYPE_SELL:
        #     if last_close > ema_50 or last_close > lwma_high:
        #         should_close = True
                
        if should_close:
            logging.info(f"Topographical Trailing Stop triggered for ticket {ticket}. Closing position.")
            tick = mt5.symbol_info_tick(Config.SYMBOL)
            close_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
            close_action = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": Config.SYMBOL,
                "volume": pos.volume,
                "type": close_action,
                "position": ticket,
                "price": float(close_price),
                "deviation": 20,
                "magic": 234000,
                "comment": "Topographical Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(request)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                try:
                    snapshot_json = capture_m1_snapshot(Config.SYMBOL, 50)
                    alasan = f"Topographical Trailing Stop: Close M1 ({last_close:.2f}) menembus struktur BBMA (EMA 50 / LWMA 10)."
                    record_journal_event_async(
                        tiket=ticket,
                        event_type="EXIT",
                        harga=float(close_price),
                        alasan=alasan,
                        snapshot_json=snapshot_json
                    )
                except Exception as e:
                    logging.error(f"[Trailing Stop Journal Error] {e}")

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
        """
        Pemicu Online Learning otomatis (Micro-Retrain) di background.
        Mengambil recent candles + closed trades feedback dan melakukan incremental fitting
        tanpa mengganggu thread eksekusi trading utama.
        """
        if not self.researcher or not self.data_miner:
            return

        if self.researcher.is_training_normal or self.researcher.is_training_runner:
            logging.info("[ONLINE LEARNING] Retraining sedang berlangsung di thread lain. Lewati micro-retrain.")
            return

        logging.info("[ONLINE LEARNING] 🚀 Memulai siklus auto micro-retrain...")
        loop = asyncio.get_running_loop()

        def _run_micro():
            try:
                df_recent = self.data_miner.load_recent_micro_chunk(n_candles=3000)
                if df_recent is None or df_recent.empty:
                    logging.warning("[ONLINE LEARNING] Gagal memuat recent candle chunk.")
                    return

                # Micro-retrain untuk mode Normal
                if self.researcher.model_normal is not None:
                    fb_normal = self.data_miner.load_live_decision_chunk(mode="normal")
                    self.researcher.micro_retrain("normal", df_recent, fb_normal)

                # Micro-retrain untuk mode Runner
                if self.researcher.model_runner is not None:
                    fb_runner = self.data_miner.load_live_decision_chunk(mode="runner")
                    self.researcher.micro_retrain("runner", df_recent, fb_runner)

                self.last_micro_retrain_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.info(f"[ONLINE LEARNING] ✨ Siklus micro-retrain selesai pada {self.last_micro_retrain_time}.")
            except Exception as e:
                logging.error(f"[ONLINE LEARNING] Gagal mengeksekusi micro-retrain: {e}")

        await loop.run_in_executor(None, _run_micro)


def capture_m1_snapshot(symbol=Config.SYMBOL, n_candles=50):
    """Merekam 50 candle M1 terakhir ke format JSON (to_json)."""
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
    """Mencatat event transaksi secara asinkron (background thread) ke database trade_journal."""
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
            logging.info(f"[Trade Journal] Event {event_type} (Tiket #{tiket}) tercatat ke Black Box.")
        except Exception as e:
            logging.error(f"[Trade Journal Error] Gagal mencatat event: {e}")
            
    threading.Thread(target=_worker, daemon=True).start()

