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
    if rates is None or len(rates) == 0:
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, timeframe_constant, start_pos, n_candles)
        if rates is None or len(rates) == 0:
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

import re

# Kamus alias umum broker
SYMBOL_ALIASES = {
    "XAUUSD": ["XAUUSD", "GOLD"],
    "XAGUSD": ["XAGUSD", "SILVER"],
    "BTCUSD": ["BTCUSD", "BTCUSDT", "BITCOIN"],
    "ETHUSD": ["ETHUSD", "ETHUSDT", "ETHEREUM"],
}

def resolve_broker_symbol(canonical_symbol="XAUUSD"):
    """
    Universal Smart Symbol Resolver:
    Menerima Canonical Symbol (misal: 'XAUUSD', 'EURUSD', 'GBPUSD', 'BTCUSD')
    dan otomatis mencari simbol broker di MT5 terlepas dari akhiran/suffix
    (misal: BTCUSDc, XAUUSDc, XAUUSDm, BTCUSD.pro, dsb).
    """
    if not canonical_symbol or str(canonical_symbol).upper() == "AUTO":
        canonical_symbol = "XAUUSD"

    clean_target = str(canonical_symbol).upper().strip()

    # 1. Exact match langsung di MT5 (hanya jika ada dan tradeable)
    info = mt5.symbol_info(clean_target)
    if info is not None and getattr(info, 'trade_mode', 0) != getattr(mt5, 'SYMBOL_TRADE_MODE_DISABLED', 0):
        mt5.symbol_select(clean_target, True)
        return clean_target

    # 2. Cari alias jika ada
    search_roots = SYMBOL_ALIASES.get(clean_target, [clean_target])

    # 3. Pindai katalog MT5
    try:
        all_symbols = mt5.symbols_get()
        if not all_symbols:
            all_symbols = mt5.symbols_get(f"*{clean_target}*")

        if all_symbols:
            candidates = []
            for s in all_symbols:
                s_name = s.name
                s_upper = s_name.upper()

                for root in search_roots:
                    pattern = rf"^{root}([._\+a-zA-Z0-9]*)$"
                    match = re.match(pattern, s_upper)
                    if match:
                        suffix = match.group(1)
                        if root == "GOLD" and any(m in suffix for m in ["MAR", "JUN", "SEP", "DEC", "24", "25", "26"]):
                            continue
                        candidates.append({
                            "name": s_name,
                            "trade_mode": getattr(s, "trade_mode", 0),
                            "visible": getattr(s, "visible", False)
                        })

            if candidates:
                tradeable = [c for c in candidates if c["trade_mode"] != getattr(mt5, 'SYMBOL_TRADE_MODE_DISABLED', 0)]
                # Prioritaskan yang visible / sudah dipilih di Market Watch jika ada
                visible_tradeable = [c for c in tradeable if c["visible"]]
                chosen = visible_tradeable[0]["name"] if visible_tradeable else (tradeable[0]["name"] if tradeable else candidates[0]["name"])
                mt5.symbol_select(chosen, True)
                return chosen
    except Exception as e:
        print(f"[resolve_broker_symbol] Gagal memindai katalog MT5: {e}")

    return clean_target

def detect_gold_symbol(preferred_symbol="AUTO"):
    """Backward compatibility wrapper untuk deteksi instrumen Gold."""
    return resolve_broker_symbol(preferred_symbol if preferred_symbol != "AUTO" else "XAUUSD")


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
    Mendeteksi apakah akun atau instrumen merupakan akun Cent (USC / EUC / XAUUSDc).
    Mencegah false positive pada mata uang dengan huruf 'c' seperti CAD dan CHF.
    """
    if symbol and str(symbol).lower().endswith("c"):
        return True
    try:
        acc = mt5.account_info()
        if acc and acc.currency:
            curr = str(acc.currency).lower().strip()
            # Hanya cocokkan kode mata uang sen standar (USC, EUC, GBC) atau yang berakhiran 'cent'/'c'
            if curr in ["usc", "euc", "gbc"] or curr.endswith("cent") or curr == "cent":
                return True
    except Exception:
        pass
    return False

def is_crypto_symbol(symbol=None):
    """
    Mendeteksi apakah sebuah instrumen merupakan aset kripto (BTC, ETH, SOL, dsb)
    yang pasarnya buka 24/7 di akhir pekan (tidak memiliki jam penutupan pasar / risiko gap akhir pekan).
    """
    if not symbol:
        return False
    s = str(symbol).upper().strip()
    crypto_keywords = [
        "BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB", "DOT",
        "AVAX", "LINK", "MATIC", "BITCOIN", "ETHEREUM", "CRYPTO"
    ]
    return any(k in s for k in crypto_keywords)
