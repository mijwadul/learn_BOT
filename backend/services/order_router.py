import time
import logging
import MetaTrader5 as mt5
from config import Config
from utils.mt5_utils import get_symbol_filling_mode, check_spread

class OrderRouter:
    """
    Pure MT5 Order Router (Institutional Execution Engine):
    - Dynamic Slippage Deviation (Spread-Adaptive)
    - Smart Requote Retry Mechanism (Max 2 retries with refreshed ticks)
    - Standardized Magic Numbers (Normal: 234001, Runner: 234002, Base: 234000)
    - Partial Close (50%) & Full Close Execution
    - Break-Even SL Synchronization
    """

    def calculate_dynamic_deviation(self, symbol: str) -> int:
        """
        P1-2: Dynamic Slippage Deviation.
        Deviation = max(20, int(Current Spread * DYNAMIC_SLIPPAGE_MULTIPLIER))
        """
        try:
            spread = check_spread(symbol) or 20
            multiplier = getattr(Config, 'DYNAMIC_SLIPPAGE_MULTIPLIER', 1.5)
            dynamic_dev = max(20, int(spread * multiplier))
            return min(dynamic_dev, 100) # Batas atas keamanan 100 points
        except Exception:
            return 20

    def send_order(
        self,
        symbol: str,
        action: int,
        lot: float,
        price: float,
        sl: float,
        tp: float,
        trade_mode: str,
        comment: str = ""
    ):
        """
        Pengiriman order transaksi MT5 dengan dynamic slippage dan smart retry saat requote.
        """
        is_runner = ("RUNNER" in trade_mode.upper())
        magic = Config.MAGIC_NUMBER_RUNNER if is_runner else Config.MAGIC_NUMBER_NORMAL
        filling_mode = get_symbol_filling_mode(symbol)
        
        max_retries = getattr(Config, 'REQUOTE_MAX_RETRIES', 2)
        current_price = price
        current_sl = sl
        current_tp = tp
        
        for attempt in range(max_retries + 1):
            deviation = self.calculate_dynamic_deviation(symbol)
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(lot),
                "type": action,
                "price": float(current_price),
                "sl": float(current_sl),
                "tp": float(current_tp),
                "deviation": deviation,
                "magic": magic,
                "comment": comment or f"AI {trade_mode}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            
            result = mt5.order_send(request)
            if result is None:
                logging.error(f"[OrderRouter] order_send() gagal, tidak ada respon MT5 (Percobaan {attempt + 1}).")
                time.sleep(0.2)
                continue
                
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logging.info(f"[OrderRouter] Order berhasil dieksekusi! Ticket: {result.order} | Deviation: {deviation} pts")
                return result
                
            # Penanganan Requote / Price Changed (10004, 10021)
            if result.retcode in (mt5.TRADE_RETCODE_REQUOTE, getattr(mt5, 'TRADE_RETCODE_PRICE_OFF', 10021)):
                logging.warning(
                    f"[OrderRouter] Requote terdeteksi (code={result.retcode}). "
                    f"Mencoba smart retry {attempt + 1}/{max_retries} dengan refresh tick..."
                )
                tick = mt5.symbol_info_tick(symbol)
                if tick:
                    diff_price = (tick.ask - current_price) if action == mt5.ORDER_TYPE_BUY else (tick.bid - current_price)
                    current_price = tick.ask if action == mt5.ORDER_TYPE_BUY else tick.bid
                    current_sl = round(current_sl + diff_price, 2)
                    current_tp = round(current_tp + diff_price, 2)
                time.sleep(0.15)
                continue
            else:
                logging.error(f"[OrderRouter] Order ditolak broker, retcode={result.retcode}")
                return result
                
        return result

    def modify_sl_to_break_even(self, ticket: int, symbol: str = None) -> bool:
        """
        Geser Stop Loss ke harga Entry (Break-Even) + 0.10 buffer spread.
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logging.warning(f"[OrderRouter] Posisi {ticket} tidak ditemukan untuk modifikasi BE.")
            return False
            
        pos = positions[0]
        sym = symbol or pos.symbol
        entry_price = pos.price_open
        buffer_pts = 0.10 if pos.type == mt5.ORDER_TYPE_BUY else -0.10
        new_sl = round(entry_price + buffer_pts, 2)
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": pos.ticket,
            "symbol": sym,
            "sl": float(new_sl),
            "tp": float(pos.tp),
        }
        
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info(f"[OrderRouter] Tiket {ticket} berhasil digeser ke Break-Even (SL: {new_sl}).")
            return True
        else:
            code = res.retcode if res else "None"
            logging.error(f"[OrderRouter] Gagal geser BE untuk tiket {ticket}, retcode: {code}")
            return False

    def execute_partial_close_50(self, ticket: int, symbol: str = None) -> bool:
        """
        Tutup 50% volume posisi aktif (Partial Profit Taking).
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False
            
        pos = positions[0]
        sym = symbol or pos.symbol
        close_volume = round(pos.volume * 0.5, 2)
        if close_volume < 0.01:
            logging.warning(f"[OrderRouter] Volume posisi {pos.volume} terlalu kecil untuk partial close 50%.")
            return False
            
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            return False
            
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        deviation = self.calculate_dynamic_deviation(sym)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": sym,
            "volume": float(close_volume),
            "type": close_type,
            "price": float(price),
            "deviation": deviation,
            "magic": Config.MAGIC_NUMBER_BASE,
            "comment": "Partial Close 50% Milestone RR 1:2",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info(f"[OrderRouter] Berhasil Partial Close 50% tiket {ticket} (Volume ditutup: {close_volume}).")
            return True
        else:
            code = res.retcode if res else "None"
            logging.error(f"[OrderRouter] Gagal Partial Close tiket {ticket}, retcode: {code}")
            return False

    def execute_full_close(self, ticket: int, reason: str = "", symbol: str = None) -> bool:
        """
        Tutup seluruh posisi aktif via MT5 Deal Order.
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return False
            
        pos = positions[0]
        sym = symbol or pos.symbol
        tick = mt5.symbol_info_tick(sym)
        if not tick:
            return False
            
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        deviation = self.calculate_dynamic_deviation(sym)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": sym,
            "volume": float(pos.volume),
            "type": close_type,
            "price": float(price),
            "deviation": deviation,
            "magic": Config.MAGIC_NUMBER_BASE,
            "comment": reason or "Full Close Position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            logging.info(f"[OrderRouter] Berhasil Full Close tiket {ticket} (Alasan: {reason}).")
            return True
        else:
            code = res.retcode if res else "None"
            logging.error(f"[OrderRouter] Gagal Full Close tiket {ticket}, retcode: {code}")
            return False
