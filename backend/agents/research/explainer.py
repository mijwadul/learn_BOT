import logging
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional


def extract_feature_importance(
    model: Any,
    features: Optional[List[str]] = None,
    top_n: int = 10,
    importance_type: str = "gain"
) -> List[Dict[str, Any]]:
    """
    Mengekstrak Top-N Feature Importance dari model LightGBM yang sudah dilatih.
    Digunakan untuk visualisasi bar chart di halaman Strategi (Dapur AI).

    Args:
        model:           Model LightGBM (sklearn wrapper atau native booster).
        features:        Daftar nama fitur (opsional, di-fallback dari model).
        top_n:           Jumlah fitur teratas yang dikembalikan.
        importance_type: 'gain' (default), 'split', atau 'shap'

    Returns:
        List of dict: [{feature, importance, rank}, ...] diurutkan descending.
    """
    if model is None:
        return []

    try:
        # Ekstrak nama fitur dari model jika tidak disuplai
        if not features:
            if hasattr(model, 'feature_name_') and model.feature_name_:
                features = list(model.feature_name_)
            elif hasattr(model, 'booster_') and hasattr(model.booster_, 'feature_name'):
                features = list(model.booster_.feature_name())
            else:
                return []

        raw_importance = None

        if importance_type == "split":
            # Split importance: jumlah berapa kali fitur dipakai sebagai pemisah pohon
            if hasattr(model, 'booster_'):
                raw_importance = model.booster_.feature_importance(importance_type='split')
            elif hasattr(model, 'feature_importances_'):
                raw_importance = model.feature_importances_
        else:
            # Gain importance (default): kontribusi rata-rata peningkatan metrik
            if hasattr(model, 'booster_'):
                raw_importance = model.booster_.feature_importance(importance_type='gain')
            elif hasattr(model, 'feature_importances_'):
                raw_importance = model.feature_importances_

        if raw_importance is None or len(raw_importance) == 0:
            return []

        # Normalisasi ke skala 0–100
        total = float(np.sum(raw_importance))
        if total <= 0:
            return []
        normalized = (raw_importance / total) * 100.0

        # Pasangkan fitur dengan importance, urutkan descending
        paired = sorted(
            zip(features[:len(normalized)], normalized),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]

        result = [
            {
                "feature": feat,
                "importance": round(float(imp), 4),
                "rank": rank + 1
            }
            for rank, (feat, imp) in enumerate(paired)
        ]
        return result

    except Exception as e:
        logging.warning(f"[extract_feature_importance] Gagal mengekstrak fitur: {e}")
        return []


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
            
        if not features:
            return "Sinyal Topografi BBMA & ATR"

        for c in features:
            if c not in X_row.columns:
                X_row[c] = 0.0
            elif not (pd.api.types.is_numeric_dtype(X_row[c]) or pd.api.types.is_bool_dtype(X_row[c])):
                X_row[c] = pd.to_numeric(X_row[c], errors='coerce').fillna(0.0)

        X_eval = X_row[features].copy()

        # Ekstrak SHAP feature contributions langsung dari LightGBM Booster
        if hasattr(model, 'booster_'):
            contribs = model.booster_.predict(X_eval, pred_contrib=True)[0]
            feat_contribs = list(zip(features, contribs[:-1]))
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
