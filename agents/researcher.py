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
        # Contoh sederhana: Target Normal (RR 1:2), Target Runner (RR 1:5)
        # Pada praktek nyata, ini menggunakan perhitungan ATR atau Lebar BB
        df['Target_Normal'] = np.where(df['close'].shift(-5) > df['close'] + 2.0, 1, 0)
        df['Target_Runner'] = np.where(df['close'].shift(-20) > df['close'] + 5.0, 1, 0)
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
