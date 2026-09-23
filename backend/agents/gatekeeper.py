import logging
import pandas as pd
from sklearn.metrics import accuracy_score

logging.basicConfig(level=logging.INFO)

class GatekeeperAgent:
    """
    Agent 3: The Gatekeeper (Out-of-Sample Validator)
    Menolak model yang overfitting melalui Chunked OOS Validation.
    """
    
    def __init__(self, researcher_agent):
        self.researcher = researcher_agent

    def validate_model(self, mode: str, test_generator, total_test_chunks: int) -> float:
        """
        Melakukan validasi model menggunakan test data generator.
        Mencatat hard negatives ke DB dan mengembalikan nilai akurasi (0.0 - 1.0).
        """
        logging.info(f"Memulai validasi Out-Of-Sample (OOS) {mode.capitalize()} Mode...")
        
        model = self.researcher.model_normal if mode == 'normal' else self.researcher.model_runner
        if model is None:
            logging.error(f"Model {mode} belum dilatih.")
            return 0.0
            
        correct, total = 0, 0
        test_chunk_idx = 1
        hn_records = []
        
        for df_test in test_generator:
            if df_test.empty: continue
            logging.info(f"[{mode.capitalize()} Mode] Validasi OOS Chunk {test_chunk_idx}/{total_test_chunks}...")
            df_test = self.researcher.generate_targets(df_test)
            
            # Gunakan subset filter spesifik BBMA Re-entry
            reentry_sell_mask = df_test['high'] >= df_test[['LWMA_5_High', 'LWMA_10_High']].min(axis=1)
            reentry_buy_mask = df_test['low'] <= df_test[['LWMA_5_Low', 'LWMA_10_Low']].max(axis=1)
            df_test = df_test[reentry_sell_mask | reentry_buy_mask].copy()
            
            if df_test.empty: continue
            
            # Pastikan kolom sesuai dengan fitur model
            for col in self.researcher.features:
                if col not in df_test.columns: df_test[col] = 0.0
                if df_test[col].dtype == 'object': df_test[col] = pd.to_numeric(df_test[col], errors='coerce')
            
            target_col = 'Target_Normal' if mode == 'normal' else 'Target_Runner'
            
            X_test = df_test[self.researcher.features]
            y_test = df_test[target_col]
            
            preds = model.predict(X_test)
            
            correct += (preds == y_test).sum()
            total += len(y_test)
            
            # Ekstrak kesalahan prediksi (Hard Negatives)
            for i in range(len(df_test)):
                if preds[i] != y_test.iloc[i]:
                    idx_time = df_test.index[i]
                    row_time_str = idx_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx_time, "strftime") else str(idx_time)
                    hn_records.append({'setup_id': row_time_str, 'failed_mode': mode.capitalize()})
                    
            test_chunk_idx += 1
            
        # Simpan Hard Negatives secara massal
        if hn_records:
            from database import bulk_add_hard_negatives
            inserted = bulk_add_hard_negatives(hn_records)
            logging.info(f"Berhasil menyimpan {inserted} baris Hard Negatives baru ke database.")
            
        accuracy = (correct / total) if total > 0 else 0.0
        logging.info(f"OOS Validation Accuracy ({mode.capitalize()} Mode): {accuracy*100:.2f}%")
        
        return accuracy
