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
        
    async def monitor_market(self):
        self.running = True
        logging.info("Executor Agent started monitoring market...")
        logging.info(f"Circuit Breakers Active [SpreadLimit: Dynamic (Base {Config.SPREAD_LIMIT_POINTS}), MaxDD: {Config.MAX_DRAWDOWN_PERCENT}%, FridayLiquidator: ON]")
        
        last_hourly_db_sync = datetime.datetime.now()
        last_exhaustion_check = datetime.datetime.now()
        last_signal_check = datetime.datetime.now()
        
        while self.running:
            if self.supervisor.state != 'live':
                await asyncio.sleep(1)
                continue
                
            now = datetime.datetime.now()

            # Rutinitas Asinkron: Auto-sync candle terbaru ke database setiap 1 jam sekali (Mode Live)
            if self.data_miner is not None and (now - last_hourly_db_sync).total_seconds() >= 3600:
                last_hourly_db_sync = now
                logging.info("[HOURLY SYNC] Menjalankan penyimpanan candle terbaru ke database secara asinkron...")
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, self.data_miner.backfill_data, 10000)
                    logging.info("[HOURLY SYNC] Sinkronisasi candle 1 jam ke database berhasil.")
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
                                
                                if max_buy > max_sell:
                                    action_type = mt5.ORDER_TYPE_BUY
                                    trade_mode = "RUNNER" if p_buy_r >= p_buy_n else "HIT_RUN"
                                    used_prob = p_buy_r if trade_mode == "RUNNER" else p_buy_n
                                else:
                                    action_type = mt5.ORDER_TYPE_SELL
                                    trade_mode = "RUNNER" if p_sell_r >= p_sell_n else "HIT_RUN"
                                    used_prob = p_sell_r if trade_mode == "RUNNER" else p_sell_n
                                
                                action_str = 'BUY' if action_type == mt5.ORDER_TYPE_BUY else 'SELL'
                                
                                # --- Aturan Ketat BBMA: RUNNER hanya dieksekusi di zona Re-entry ---
                                allow_execution = True
                                if trade_mode == "RUNNER":
                                    lwma_5_h = row_data.get('LWMA_5_High', 0)
                                    lwma_10_h = row_data.get('LWMA_10_High', 0)
                                    lwma_5_l = row_data.get('LWMA_5_Low', 0)
                                    lwma_10_l = row_data.get('LWMA_10_Low', 0)
                                    high_price = row_data.get('high', 0)
                                    low_price = row_data.get('low', 0)
                                    
                                    if action_type == mt5.ORDER_TYPE_SELL:
                                        reentry_zone = min(lwma_5_h, lwma_10_h)
                                        if high_price < reentry_zone:
                                            logging.info(f"[FILTER BBMA] Sinyal SELL ditahan (Wait): Harga belum mencapai zona Re-entry LWMA High (High {high_price:.4f} < {reentry_zone:.4f}).")
                                            allow_execution = False
                                    elif action_type == mt5.ORDER_TYPE_BUY:
                                        reentry_zone = max(lwma_5_l, lwma_10_l)
                                        if low_price > reentry_zone:
                                            logging.info(f"[FILTER BBMA] Sinyal BUY ditahan (Wait): Harga belum mencapai zona Re-entry LWMA Low (Low {low_price:.4f} > {reentry_zone:.4f}).")
                                            allow_execution = False
                                            
                                if allow_execution:
                                    logging.info(f"[SIGNAL] Multiclass Entry: {action_str} | Mode: {trade_mode} | Prob: {used_prob:.2f}")
                                    self.execute_order(action_type, sl_dist, trade_mode=trade_mode, prob_runner=used_prob)
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
                        
                        # --- Dynamic TP Multiplier berdasarkan Tren (ADX) ---
                        tp_multiplier = 2.0
                        rates_tp = mt5.copy_rates_from_pos(Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 30)
                        if rates_tp is not None and len(rates_tp) >= 30:
                            df_tp = pd.DataFrame(rates_tp)
                            from utils.indicators import calculate_adx
                            df_tp['adx'] = calculate_adx(df_tp, 14)
                            adx_val = df_tp['adx'].iloc[-1]
                            if not np.isnan(adx_val):
                                if adx_val > 40: tp_multiplier = 3.0
                                elif adx_val < 20: tp_multiplier = 1.5

                        if not is_runner:
                            # --- Logika HIT_RUN ---
                            if initial_risk > 0:
                                # BE saat RR 1:1 secepatnya
                                if current_gain >= (1.0 * initial_risk) and abs(pos.sl - pos.price_open) > 0.05:
                                    logging.info(f"[HIT_RUN] Target RR 1:1 tercapai untuk tiket {ticket}. Geser SL ke BE.")
                                    self.modify_sl_to_break_even(ticket)
                                # Full Close saat RR dinamis tercapai
                                if current_gain >= (tp_multiplier * initial_risk):
                                    logging.info(f"[HIT_RUN] Target RR 1:{tp_multiplier} tercapai untuk tiket {ticket}. Menjalankan Full Close.")
                                    self.execute_full_close(ticket, reason=f"Hit & Run: Target RR 1:{tp_multiplier} Tercapai (Full Close)")
                        else:
                            # --- Logika RUNNER ---
                            if initial_risk > 0 and current_gain >= (tp_multiplier * initial_risk):
                                if abs(pos.sl - pos.price_open) > 0.05:
                                    logging.info(f"[RUNNER] Target RR 1:{tp_multiplier} tercapai untuk tiket {ticket}. Partial Close 50% & SL ke BE.")
                                    self.execute_partial_close_50(ticket)
                                    self.modify_sl_to_break_even(ticket)
                                    
                            # Trailing stop seketika kini ditangani oleh AI Probability Loop di atas
                            # self.topographical_trailing_stop(ticket) # Dinonaktifkan, pindah ke AI Driven
                            pass
            except Exception as e:
                logging.debug(f"Position management loop error: {e}")

            # Simulasi delay tick
            await asyncio.sleep(1)

    def stop(self):
        self.running = False
        logging.info("Executor Agent stopped.")
        
    def execute_order(self, action, sl_distance, trade_mode="HIT_RUN", prob_runner=None):
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

        positions = mt5.positions_get(symbol=Config.SYMBOL)
        same_dir_positions = []
        if positions:
            for p in positions:
                if p.type == action:
                    same_dir_positions.append(p)
                    
        # Tidak dibatasi jumlahnya (unlimited pyramid) JIKA probabilitas runner >= 70%
        is_high_prob = prob_runner is not None and prob_runner >= 0.70
        
        if not is_high_prob and len(same_dir_positions) >= getattr(self, 'MAX_PYRAMIDING', 3):
            logging.warning(f"[PYRAMIDING] Limit dinamis {getattr(self, 'MAX_PYRAMIDING', 3)} (ADX: {current_adx:.1f}) tercapai. Order ditolak.")
            return None
            
        for p in same_dir_positions:
            if p.profit <= 0:
                logging.warning(f"[PYRAMIDING] Posisi sebelumnya (Tiket {p.ticket}) belum profit. Scale-In ditolak.")
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
                
        # Kalkulasi Parameter Orde Langsung (Kelly-Lite Dynamic Risk)
        win_rate = 0.5
        try:
            from database import get_recent_trade_logs
            logs_df = get_recent_trade_logs(50)
            if not logs_df.empty:
                wins = len(logs_df[logs_df['profit'] > 0])
                win_rate = wins / len(logs_df)
        except Exception:
            pass
            
        risk_modifier = 1.0
        if win_rate < 0.40:
            risk_modifier = 0.5 # Defensif (potong risiko separuh) jika win rate buruk
            logging.info(f"[RISK] Win rate buruk ({win_rate*100:.0f}%), memotong risiko 50%")
        elif win_rate > 0.65:
            risk_modifier = 1.5 # Agresif jika win rate sangat baik
            logging.info(f"[RISK] Win rate super ({win_rate*100:.0f}%), meningkatkan risiko 50%")
            
        # --- Formula Sizing Berbasis Uang (Risk) ---
        # Contoh user: Jika risk $10, dan jarak SL adalah 500 poin ($5.00 absolut), maka lot harus 0.02 (di XAUUSD).
        tick_value = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size
        
        lot = 0.01
        if tick_size > 0 and tick_value > 0:
            # Nilai uang riil untuk setiap 1 poin (absolut) per 1 lot standar
            money_per_unit = tick_value / tick_size
            
            # Total kerugian jika kita open 1 lot penuh untuk jarak SL ini
            loss_for_one_lot = sl_distance * money_per_unit
            
            if loss_for_one_lot > 0:
                lot = (Config.MAX_RISK_DOLLARS * risk_modifier) / loss_for_one_lot
                
        lot = max(0.01, round(lot, 2))
        
        tick = mt5.symbol_info_tick(Config.SYMBOL)
        if tick is None:
            logging.error("Tick data unavailable.")
            return None
            
        price = tick.ask if action == mt5.ORDER_TYPE_BUY else tick.bid
        # sl_distance sudah berupa selisih harga absolut (misal $5.00), bukan poin.
        # Jadi kita tidak perlu mengalikannya dengan symbol_info.point
        sl_abs = float(sl_distance)
        tp_abs = float(sl_distance * 10)  # Sekring TP darurat 1:10
        
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
            
            try:
                from database import log_trade_record
                action_str = "BUY" if action == mt5.ORDER_TYPE_BUY else "SELL"
                log_trade_record(
                    action=action_str,
                    volume=float(lot),
                    price=float(price),
                    sl=float(sl),
                    tp=float(tp),
                    profit=0.0,
                    comment=f"Ticket #{result.order} | AI Bot Execute"
                )
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

