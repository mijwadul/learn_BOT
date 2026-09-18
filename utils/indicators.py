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
    df['BB_Width'] = df['BB_Upper'] - df['BB_Lower']
    df['dist_LWMA_High_BB_Upper'] = df['LWMA_5_High'] - df['BB_Upper']
    
    return df
