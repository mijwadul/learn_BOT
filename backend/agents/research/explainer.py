import logging
import numpy as np
import pandas as pd

def get_top_feature_contributions(model, features, X_row, top_n=3) -> str:
    """
    XAI (Explainable AI):
    Mengekstrak Top 3 Feature Contributions dari model LightGBM untuk keputusan eksekusi.
    """
    if model is None:
        return "Sinyal Breakout Topografi BBMA & ATR"

    try:
        if isinstance(X_row, pd.Series):
            X_row = pd.DataFrame([X_row])
            
        valid_cols = [c for c in features if c in X_row.columns]
        if not valid_cols:
            return "Sinyal Topografi BBMA & ATR"
            
        X_eval = X_row[valid_cols]
        
        # Ekstrak SHAP feature contributions langsung dari LightGBM Booster
        if hasattr(model, 'booster_'):
            contribs = model.booster_.predict(X_eval, pred_contrib=True)[0]
            feat_contribs = list(zip(valid_cols, contribs[:-1]))
            top_features = sorted(feat_contribs, key=lambda x: abs(x[1]), reverse=True)[:top_n]
            
            parts = []
            for feat, val in top_features:
                sign = "+" if val >= 0 else ""
                parts.append(f"{feat} ({sign}{val:.2f})")
            return "Top 3 Fitur: " + ", ".join(parts)
    except Exception as e:
        logging.debug(f"Gagal kalkulasi feature contribution SHAP: {e}")

    try:
        if hasattr(model, 'feature_importances_'):
            top_idx = np.argsort(model.feature_importances_)[-top_n:][::-1]
            top_f = [features[i] for i in top_idx]
            return "Top 3 Fitur Utama: " + ", ".join(top_f)
    except Exception:
        pass

    return "BBMA Convergence & Momentum ATR"
