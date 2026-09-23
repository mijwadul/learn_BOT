import MetaTrader5 as mt5
import pandas as pd
import os
import subprocess

def init_mt5(server, login, password, path=""):
    kwargs = {}
    if path and os.path.exists(path):
        kwargs["path"] = path

    if login == 0 or not password:
        # Connect to the currently active MT5 terminal
        success = mt5.initialize(**kwargs)
    else:
        # Connect to a specific account
        success = mt5.initialize(server=server, login=login, password=password, **kwargs)
        
    if not success:
        print(f"initialize() failed, error code = {mt5.last_error()}")
        return False
        
    if path and os.path.exists(path):
        try:
            subprocess.Popen([path])
        except Exception as e:
            print(f"Failed to focus MT5: {e}")
            
    print("MT5 Initialized Successfully.")
    return True

def get_rates(symbol, timeframe_constant, n_candles=1000, start_pos=0):
    """
    timeframe_constant: e.g. mt5.TIMEFRAME_M1
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe_constant, start_pos, n_candles)
    if rates is None:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def check_spread(symbol):
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return None
    return symbol_info.spread

def shutdown_mt5():
    mt5.shutdown()

def detect_gold_symbol(preferred_symbol="AUTO"):
    """
    Cerdas mendeteksi symbol Gold yang aktif/tersedia di broker MT5.
    Mendukung XAUUSD, XAUUSDm, XAUUSDc, GOLD, XAUUSD.a, dsb.
    """
    # 1. Jika user menetapkan symbol spesifik selain "AUTO"
    if preferred_symbol and str(preferred_symbol).upper() != "AUTO":
        info = mt5.symbol_info(preferred_symbol)
        if info is not None:
            mt5.symbol_select(preferred_symbol, True)
            return preferred_symbol

    # 2. Prioritas pengecekan kandidat umum di berbagai broker (Exness, IC Markets, XM, dsb)
    candidates = [
        "XAUUSD", "XAUUSDm", "XAUUSDc", "XAUUSD.a", "XAUUSD+", "XAUUSD.pro", 
        "GOLD", "GOLDm", "GOLDc", "XAUUSDmicro"
    ]
    for sym in candidates:
        info = mt5.symbol_info(sym)
        if info is not None:
            mt5.symbol_select(sym, True)
            return sym

    # 3. Cari dari seluruh katalog simbol di MT5 yang mengandung kata XAUUSD atau GOLD
    try:
        all_symbols = mt5.symbols_get()
        if all_symbols:
            for s in all_symbols:
                name_upper = s.name.upper()
                if "XAUUSD" in name_upper:
                    mt5.symbol_select(s.name, True)
                    return s.name
            for s in all_symbols:
                name_upper = s.name.upper()
                if "GOLD" in name_upper and not any(m in name_upper for m in ["MAR", "JUN", "SEP", "DEC"]):
                    mt5.symbol_select(s.name, True)
                    return s.name
    except Exception as e:
        print(f"[detect_gold_symbol] Gagal memindai katalog MT5: {e}")

    # Fallback aman
    return "XAUUSD"

def get_symbol_filling_mode(symbol):
    """
    Deteksi cerdas Filling Mode order MT5 (IOC, FOK, RETURN)
    berdasarkan kapabilitas instrumen broker (mencegah error 10030: Unsupported filling mode).
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC
        
    filling = getattr(info, 'filling_mode', 0)
    # SYMBOL_FILLING_IOC = 2
    if filling & 2:
        return mt5.ORDER_FILLING_IOC
    # SYMBOL_FILLING_FOK = 1
    elif filling & 1:
        return mt5.ORDER_FILLING_FOK
    else:
        # Fallback standar pasar / return
        return getattr(mt5, 'ORDER_FILLING_RETURN', 2)

def is_cent_account(symbol=None):
    """
    Mendeteksi apakah akun atau instrumen merupakan akun Cent (USC / XAUUSDc).
    """
    if symbol and str(symbol).lower().endswith("c"):
        return True
    try:
        acc = mt5.account_info()
        if acc and acc.currency:
            curr = str(acc.currency).lower()
            if "c" in curr or "cent" in curr:
                return True
    except Exception:
        pass
    return False
