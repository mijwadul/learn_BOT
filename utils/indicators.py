import pandas as pd
import numpy as np

def calculate_sma(series, length):
    return series.rolling(window=length).mean()

def calculate_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def calculate_lwma(series, length):
    weights = np.arange(1, length + 1)
    return series.rolling(window=length).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)

def calculate_atr(df, length=14):
    df_copy = df.copy()
    df_copy['H-L'] = df_copy['high'] - df_copy['low']
    df_copy['H-PC'] = abs(df_copy['high'] - df_copy['close'].shift(1))
    df_copy['L-PC'] = abs(df_copy['low'] - df_copy['close'].shift(1))
    df_copy['TR'] = df_copy[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    return df_copy['TR'].rolling(window=length).mean()

def calculate_adx(df, length=14):
    df_copy = df.copy()
    df_copy['up_move'] = df_copy['high'] - df_copy['high'].shift(1)
    df_copy['down_move'] = df_copy['low'].shift(1) - df_copy['low']
    
    df_copy['+dm'] = np.where((df_copy['up_move'] > df_copy['down_move']) & (df_copy['up_move'] > 0), df_copy['up_move'], 0.0)
    df_copy['-dm'] = np.where((df_copy['down_move'] > df_copy['up_move']) & (df_copy['down_move'] > 0), df_copy['down_move'], 0.0)
    
    tr = df_copy[['high']].copy()
    tr['H-L'] = df_copy['high'] - df_copy['low']
    tr['H-PC'] = abs(df_copy['high'] - df_copy['close'].shift(1))
    tr['L-PC'] = abs(df_copy['low'] - df_copy['close'].shift(1))
    df_copy['tr'] = tr[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    
    atr = df_copy['tr'].ewm(alpha=1/length, adjust=False).mean()
    plus_di = 100 * (df_copy['+dm'].ewm(alpha=1/length, adjust=False).mean() / atr)
    minus_di = 100 * (df_copy['-dm'].ewm(alpha=1/length, adjust=False).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    return dx.ewm(alpha=1/length, adjust=False).mean()

def calculate_bbma(df):
    """
    Menghitung topografi BBMA berdasarkan spesifikasi:
    - Bollinger Bands (20, 2)
    - EMA (50, Close)
    - LWMA High (5, 10)
    - LWMA Low (5, 10)
    """
    df = df.copy()
    
    # Bollinger Bands
    df['SMA_20'] = calculate_sma(df['close'], 20)
    std = df['close'].rolling(window=20).std()
    df['BB_Upper'] = df['SMA_20'] + (std * 2)
    df['BB_Lower'] = df['SMA_20'] - (std * 2)
    
    # EMA
    df['EMA_50'] = calculate_ema(df['close'], 50)
    
    # LWMA
    df['LWMA_5_High'] = calculate_lwma(df['high'], 5)
    df['LWMA_10_High'] = calculate_lwma(df['high'], 10)
    df['LWMA_5_Low'] = calculate_lwma(df['low'], 5)
    df['LWMA_10_Low'] = calculate_lwma(df['low'], 10)
    
    # Jarak Topografi
    df['dist_Close_EMA50'] = df['close'] - df['EMA_50']
    df['dist_Close_SMA20'] = df['close'] - df['SMA_20']
    df['BB_Width'] = df['BB_Upper'] - df['BB_Lower']
    df['dist_LWMA_High_BB_Upper'] = df['LWMA_5_High'] - df['BB_Upper']
    
    # Kemiringan / Deteksi Sideways (MHV) - Rate of Change (ROC) selama 3 candle
    df['SMA_20_Slope'] = df['SMA_20'] - df['SMA_20'].shift(3)
    df['BB_Width_Slope'] = df['BB_Width'] - df['BB_Width'].shift(3)
    
    # Deteksi Momentum (CSM)
    df['is_CSM_Buy'] = np.where(df['close'] > df['BB_Upper'], 1, 0)
    df['is_CSM_Sell'] = np.where(df['close'] < df['BB_Lower'], 1, 0)
    
    # Arah Tren LWMA (Crossover)
    df['LWMA_Crossover_High'] = df['LWMA_5_High'] - df['LWMA_10_High']
    df['LWMA_Crossover_Low'] = df['LWMA_5_Low'] - df['LWMA_10_Low']
    
    # Karakteristik Candlestick (Pola Ekor & Body)
    df['upper_wick'] = df['high'] - np.maximum(df['open'], df['close'])
    df['lower_wick'] = np.minimum(df['open'], df['close']) - df['low']
    df['body_size'] = np.abs(df['close'] - df['open'])
    df['candle_dir'] = np.where(df['close'] >= df['open'], 1, -1)
    
    # Deteksi Pola Engulfing
    df['prev_open'] = df['open'].shift(1)
    df['prev_close'] = df['close'].shift(1)
    
    # Bullish Engulfing: previous is red, current is green, current body engulfs previous
    df['is_Bullish_Engulfing'] = np.where(
        (df['prev_close'] < df['prev_open']) & 
        (df['close'] > df['open']) & 
        (df['close'] >= df['prev_open']) & 
        (df['open'] <= df['prev_close']), 
        1, 0
    )
    
    # Bearish Engulfing: previous is green, current is red, current body engulfs previous
    df['is_Bearish_Engulfing'] = np.where(
        (df['prev_close'] > df['prev_open']) & 
        (df['close'] < df['open']) & 
        (df['close'] <= df['prev_open']) & 
        (df['open'] >= df['prev_close']), 
        1, 0
    )
    
    # Drop temp columns used for engulfing
    df.drop(columns=['prev_open', 'prev_close'], inplace=True)
    
    return df
