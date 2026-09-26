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
                sym_info = mt5.symbol_info(symbol)
                digits = sym_info.digits if sym_info and sym_info.digits else 2
                if tick:
                    diff_price = (tick.ask - current_price) if action == mt5.ORDER_TYPE_BUY else (tick.bid - current_price)
                    current_price = tick.ask if action == mt5.ORDER_TYPE_BUY else tick.bid
                    current_sl = round(current_sl + diff_price, digits)
                    current_tp = round(current_tp + diff_price, digits)
                time.sleep(0.15)
                continue
            else:
                logging.error(f"[OrderRouter] Order ditolak broker, retcode={result.retcode}")
                return result
                
        return result

    def modify_sl_to_break_even(self, ticket: int, symbol: str = None) -> bool:
        """
        Geser Stop Loss ke harga Entry (Break-Even) dengan buffer adaptif spread (min 0.30 untuk Gold / 2x spread).
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logging.warning(f"[OrderRouter] Posisi {ticket} tidak ditemukan untuk modifikasi BE.")
            return False
            
        pos = positions[0]
        sym = symbol or pos.symbol
        entry_price = pos.price_open
        
        sym_info = mt5.symbol_info(sym)
        digits = sym_info.digits if sym_info and sym_info.digits else 2
        point = sym_info.point if sym_info and sym_info.point else 0.01
        spread = sym_info.spread if sym_info and sym_info.spread else 20
        
        spread_dist = spread * point
        min_buffer = 30 * point if point > 0 else 0.0003
        buffer_raw = max(min_buffer, round(spread_dist * 2.0, digits))
        buffer_pts = buffer_raw if pos.type == mt5.ORDER_TYPE_BUY else -buffer_raw
        new_sl = round(entry_price + buffer_pts, digits)
        
        # Cek jika SL saat ini sudah berada di Break-Even atau lebih menguntungkan
        if pos.type == mt5.ORDER_TYPE_BUY and pos.sl >= new_sl:
            logging.debug(f"[OrderRouter] Tiket {ticket} SL sudah di Break-Even ({pos.sl} >= {new_sl}). Tidak perlu kirim request.")
            return True
        elif pos.type == mt5.ORDER_TYPE_SELL and 0 < pos.sl <= new_sl:
            logging.debug(f"[OrderRouter] Tiket {ticket} SL sudah di Break-Even ({pos.sl} <= {new_sl}). Tidak perlu kirim request.")
            return True

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": pos.ticket,
            "symbol": sym,
            "sl": float(new_sl),
            "tp": float(pos.tp),
        }
        
        res = mt5.order_send(request)
        retcode_no_changes = getattr(mt5, 'TRADE_RETCODE_NO_CHANGES', 10025)
        if res and res.retcode in [mt5.TRADE_RETCODE_DONE, retcode_no_changes]:
            if res.retcode == retcode_no_changes:
                logging.info(f"[OrderRouter] Tiket {ticket} sudah berada pada Break-Even di broker ({new_sl}), retcode 10025 (No Changes).")
            else:
                logging.info(f"[OrderRouter] Tiket {ticket} berhasil digeser ke Break-Even (Entry: {entry_price}, Buffer: {buffer_pts:+.2f}, New SL: {new_sl}).")
            return True
        else:
            code = res.retcode if res else "None"
            logging.error(f"[OrderRouter] Gagal geser BE untuk tiket {ticket}, retcode: {code}")
            return False

    def _send_close_deal(self, pos, sym: str, volume: float, close_type: int, comment: str = "", max_retries: int = 2) -> bool:
        """
        Helper eksekusi deal close MT5 tingkat institusional:
        - Adaptive Filling Mode Fallback Matrix (symbol preference -> RETURN -> IOC -> FOK)
        - Dynamic Slippage & Adaptive Requote Retries (refresh tick)
        - MT5 Protocol Comment Sanitization (max 31 chars)
        """
        sanitized_comment = str(comment or "Close Position")[:31]
        primary_filling = get_symbol_filling_mode(sym)
        
        # Matrix fallback filling mode jika broker menolak dengan retcode 10030 (INVALID_FILL)
        candidate_fillings = [primary_filling]
        for f_mode in [
            getattr(mt5, 'ORDER_FILLING_RETURN', 2),
            mt5.ORDER_FILLING_IOC,
            mt5.ORDER_FILLING_FOK
        ]:
            if f_mode not in candidate_fillings:
                candidate_fillings.append(f_mode)
                
        for attempt in range(max_retries + 1):
            tick = mt5.symbol_info_tick(sym)
            if not tick:
                time.sleep(0.1)
                continue
                
            price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            deviation = self.calculate_dynamic_deviation(sym)
            
            # Coba candidate filling modes jika terjadi invalid filling
            last_res = None
            executed = False
            for filling_mode in candidate_fillings:
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": pos.ticket,
                    "symbol": sym,
                    "volume": float(volume),
                    "type": close_type,
                    "price": float(price),
                    "deviation": deviation,
                    "magic": Config.MAGIC_NUMBER_BASE,
                    "comment": sanitized_comment,
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": filling_mode,
                }
                
                res = mt5.order_send(request)
                last_res = res
                
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    executed = True
                    break
                elif res and res.retcode == getattr(mt5, 'TRADE_RETCODE_INVALID_FILL', 10030):
                    # Broker menolak filling mode ini, coba candidate fallback berikutnya
                    continue
                else:
                    # Bukan error filling mode (misal requote, price changed, dll)
                    break
                    
            if executed:
                return True
                
            if last_res and last_res.retcode in (
                mt5.TRADE_RETCODE_REQUOTE,
                getattr(mt5, 'TRADE_RETCODE_PRICE_OFF', 10021)
            ):
                logging.warning(
                    f"[OrderRouter] Requote saat close tiket #{pos.ticket} (code={last_res.retcode}). "
                    f"Retry {attempt + 1}/{max_retries} dengan refresh tick..."
                )
                time.sleep(0.15)
                continue
            else:
                code = last_res.retcode if last_res else "None"
                logging.error(f"[OrderRouter] Gagal close tiket #{pos.ticket}, retcode: {code}")
                time.sleep(0.1)
                
        return False

    def execute_partial_close_50(self, ticket: int, symbol: str = None) -> bool:
        """
        Tutup 50% volume posisi aktif (Partial Profit Taking) tingkat institusional.
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logging.warning(f"[OrderRouter] Posisi tiket #{ticket} tidak ditemukan untuk partial close.")
            return False
            
        pos = positions[0]
        sym = symbol or pos.symbol
        close_volume = round(pos.volume * 0.5, 2)
        if close_volume < 0.01:
            logging.warning(f"[OrderRouter] Volume posisi {pos.volume} terlalu kecil untuk partial close 50%.")
            return False
            
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        max_retries = getattr(Config, 'REQUOTE_MAX_RETRIES', 2)
        success = self._send_close_deal(pos, sym, close_volume, close_type, "Partial Close 50%", max_retries=max_retries)
        if success:
            logging.info(f"[OrderRouter] ✅ Berhasil Partial Close 50% tiket #{ticket} (Volume: {close_volume}).")
        return success

    def execute_full_close(self, ticket: int, reason: str = "", symbol: str = None) -> bool:
        """
        Tutup seluruh posisi aktif via MT5 Deal Order dengan jaminan eksekusi institusional.
        """
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            logging.warning(f"[OrderRouter] Posisi tiket #{ticket} tidak ditemukan untuk full close.")
            return False
            
        pos = positions[0]
        sym = symbol or pos.symbol
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        max_retries = getattr(Config, 'REQUOTE_MAX_RETRIES', 2)
        success = self._send_close_deal(pos, sym, pos.volume, close_type, reason or "Full Close", max_retries=max_retries)
        if success:
            logging.info(f"[OrderRouter] ✅ Berhasil Full Close tiket #{ticket} (Alasan: {reason}).")
        return success
