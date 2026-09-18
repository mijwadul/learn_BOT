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
    
    def __init__(self, supervisor_agent):
        self.supervisor = supervisor_agent
        self.running = False
        
    async def monitor_market(self):
        self.running = True
        logging.info("Executor Agent started monitoring market...")
        logging.info(f"Circuit Breakers Active [SpreadLimit: {Config.SPREAD_LIMIT_POINTS}, MaxDD: {Config.MAX_DRAWDOWN_PERCENT}%, FridayLiquidator: ON]")
        
        while self.running:
            if self.supervisor.state != 'live':
                await asyncio.sleep(1)
                continue
                
            # Cek Friday Liquidator
            now = datetime.datetime.now()
            if now.weekday() == 4 and now.hour >= 23:
                logging.warning("[SEKRING] Friday Liquidator Active! Closing all positions.")
                self.supervisor.trigger_friday_liquidator()
                # logika close all via MT5
                await asyncio.sleep(60) 
                continue
                
            # Cek status sekring Spread
            spread = check_spread(Config.SYMBOL)
            if spread is not None and spread > Config.SPREAD_LIMIT_POINTS:
                logging.warning(f"[SEKRING] Eksekusi ditolak: Spread {spread} poin melebihi batas {Config.SPREAD_LIMIT_POINTS}")
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

            # Simulasi delay tick
            await asyncio.sleep(1)

    def stop(self):
        self.running = False
        logging.info("Executor Agent stopped.")
        
    def execute_order(self, action, sl_distance):
        # Tick Volatility Anomaly Circuit Breaker
        rates = mt5.copy_rates_from_pos(Config.SYMBOL, mt5.TIMEFRAME_M1, 0, 15)
        if rates is not None and len(rates) >= 15:
            df_rates = pd.DataFrame(rates)
            df_rates['TR'] = np.maximum(
                df_rates['high'] - df_rates['low'],
                np.maximum(
                    abs(df_rates['high'] - df_rates['close'].shift(1)),
                    abs(df_rates['low'] - df_rates['close'].shift(1))
                )
            )
            atr_14 = df_rates['TR'].rolling(14).mean().iloc[-1]
            last_candle_range = df_rates['high'].iloc[-2] - df_rates['low'].iloc[-2] # Gunakan candle M1 yang baru saja ditutup utuh
            
            if last_candle_range > 3 * atr_14:
                logging.warning(f"[SEKRING] Volatility Anomaly! Range {last_candle_range:.5f} > 3x ATR ({3*atr_14:.5f}). Order rejected.")
                return None

        point_value = 1.0 
        sl_distance = max(sl_distance, 1.0)
        lot = Config.MAX_RISK_DOLLARS / (sl_distance * point_value)
        lot = max(0.01, round(lot, 2))
        logging.info(f"Executing {action} order with {lot:.2f} Lot.")
        
        symbol_info = mt5.symbol_info(Config.SYMBOL)
        if symbol_info is None:
            logging.error(f"{Config.SYMBOL} not found, can not call order_check()")
            return None
            
        if not symbol_info.visible:
            logging.error(f"{Config.SYMBOL} is not visible, trying to switch on")
            if not mt5.symbol_select(Config.SYMBOL, True):
                logging.error(f"symbol_select({Config.SYMBOL}) failed, exit")
                return None
                
        point = symbol_info.point
        tick = mt5.symbol_info_tick(Config.SYMBOL)
        price = tick.ask if action == mt5.ORDER_TYPE_BUY else tick.bid
        
        sl_points = sl_distance * point
        tp_points = sl_distance * 10 * point  # Sekring TP darurat 1:10
        
        if action == mt5.ORDER_TYPE_BUY:
            sl = price - sl_points
            tp = price + tp_points
        else:
            sl = price + sl_points
            tp = price - tp_points
            
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
            "comment": "AI Bot Execute",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result is None:
            logging.error("order_send() failed, no result returned.")
        elif result.retcode != mt5.TRADE_RETCODE_DONE:
            logging.error(f"Order failed, retcode={result.retcode}")
        else:
            logging.info(f"Order placed successfully! Ticket: {result.order}")
        return result

    def execute_partial_close_50(self, ticket):
        """
        Skeleton untuk eksekusi Partial Close 50% dari volume.
        """
        logging.info(f"Executing 50% partial close for ticket {ticket}")
        pass

    def modify_sl_to_break_even(self, ticket):
        """
        Skeleton untuk modifikasi Stop Loss ke Break Even (harga open) jika mode Trend Rider aktif.
        """
        logging.info(f"Modifying SL to Break Even for ticket {ticket}")
        pass
        
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
        if pos.type == mt5.ORDER_TYPE_BUY:
            if last_close < ema_50 or last_close < lwma_low:
                should_close = True
        elif pos.type == mt5.ORDER_TYPE_SELL:
            if last_close > ema_50 or last_close > lwma_high:
                should_close = True
                
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
            mt5.order_send(request)
