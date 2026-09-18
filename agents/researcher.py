import logging
import lightgbm as lgb
from sklearn.model_selection import train_test_split
import numpy as np

logging.basicConfig(level=logging.INFO)

class ResearcherAgent:
    """
    Agent 2: The Researcher (Dual-Target AI Brain)
    Melatih algoritma (LightGBM) menggunakan target dinamis.
    """
    
    def __init__(self):
        self.model_normal = None
        self.model_runner = None
        self.features = []
        
    def generate_targets(self, df):
        from utils.indicators import calculate_atr
        df['ATR_14'] = calculate_atr(df, 14)
        
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        atrs = df['ATR_14'].values
        
        n = len(df)
        labels_normal = np.zeros(n)
        
        # Look forward up to 100 candles
        for i in range(n):
            if np.isnan(atrs[i]):
                continue
                
            sl_dist = atrs[i]
            tp_dist = sl_dist * 2.0
            entry_price = closes[i]
            
            tp_level = entry_price + tp_dist
            sl_level = entry_price - sl_dist
            
            for j in range(i + 1, min(i + 101, n)):
                if lows[j] <= sl_level:
                    labels_normal[i] = 0
                    break
                if highs[j] >= tp_level:
                    labels_normal[i] = 1
                    break
                    
        df['Target_Normal'] = labels_normal
        df['Target_Runner'] = np.where(df['close'].shift(-20) > df['close'] + 5.0, 1, 0)
        
        # Drop temporary ATR column if not used as feature, or keep it
        return df

    def train_models(self, df):
        logging.info("Training LightGBM Dual-Target models...")
        df = self.generate_targets(df)
        df = df.dropna()
        
        # Features (excluding target columns)
        self.features = [col for col in df.columns if 'Target' not in col]
        X = df[self.features]
        
        y_normal = df['Target_Normal']
        y_runner = df['Target_Runner']
        
        # Train Normal Model
        self.model_normal = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, random_state=42)
        self.model_normal.fit(X, y_normal)
        
        # Train Runner Model
        self.model_runner = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.05, random_state=42)
        self.model_runner.fit(X, y_runner)
        
        logging.info("Models trained successfully.")
        return True
