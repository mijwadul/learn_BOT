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
