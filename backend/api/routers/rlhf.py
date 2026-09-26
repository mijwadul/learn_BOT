import logging
import asyncio
import numpy as np
import pandas as pd
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from config import Config
from ..dependencies import bot

router = APIRouter(tags=["RLHF Human Feedback"])

class RLHFRequest(BaseModel):
    setup_id: str
    decision: str # "approve", "reject", or "ignore"
    symbol: Optional[str] = "XAUUSD"
    action_type: Optional[str] = "BUY"
    probability: Optional[float] = 0.0
    notes: Optional[str] = ""
    mode: Optional[str] = "normal"

@router.post("/api/rlhf/feedback")
async def submit_rlhf(req: RLHFRequest):
    try:
        from database import save_approved_setup, save_rejected_setup, save_ignored_setup
        mode_val = req.mode.lower() if req.mode else "normal"
        logging.info(f"Menerima RLHF Feedback: {req.decision.upper()} [{mode_val.upper()}] untuk {req.setup_id}")
        
        if req.decision == "approve":
            await asyncio.to_thread(save_approved_setup, req.setup_id, req.symbol, req.action_type, req.probability, req.notes, mode=mode_val)
        elif req.decision == "reject":
            await asyncio.to_thread(save_rejected_setup, req.setup_id, req.symbol, req.action_type, req.probability, req.notes, mode=mode_val)
        elif req.decision == "ignore":
            await asyncio.to_thread(save_ignored_setup, req.setup_id, req.symbol, req.action_type, req.probability, req.notes, mode=mode_val)
        else:
            return {"status": "error", "message": f"Decision tidak valid: {req.decision}. Gunakan approve/reject/ignore."}
        return {"status": "success", "message": f"Setup {req.setup_id} marked as {req.decision} ({mode_val})."}
    except Exception as e:
        logging.error(f"RLHF error: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/api/rlhf/setups")
async def get_rlhf_setups(min_prob: float = 0.65, offset: int = 0, mode: str = "normal", symbol: Optional[str] = None):
    """
    Review Queue: Kembalikan 1 setup OOS per request berdasarkan offset dan mode (normal vs runner).
    """
    def _fetch():
        from database import sync_engine, get_approved_setup_ids, get_rejected_setup_ids, get_ignored_setup_ids, get_market_table_name
        mode_str = mode.lower() if mode else "normal"
        sym = (symbol or getattr(bot.researcher, "symbol", "XAUUSD")).upper()
        table_name = get_market_table_name(sym)

        # Cek apakah tabel ada, jika tidak fallback ke market_data_merged untuk xauusd
        try:
            query_count = f'SELECT COUNT(*) FROM "{table_name}"'
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
        except Exception:
            table_name = "market_data_merged"
            try:
                query_count = f'SELECT COUNT(*) FROM "{table_name}"'
                total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            except Exception:
                total_rows = 0

        if total_rows < 100:
            return {"status": "error", "message": f"Database {sym} kosong. Jalankan Force Backfill MT5 terlebih dahulu.", "setup": None, "total": 0}

        split_idx = int(total_rows * 0.8)
        
        target_model = bot.researcher.model_normal if mode_str == "normal" else bot.researcher.model_runner
        if target_model is not None:
            df_full_oos = pd.read_sql(
                f'SELECT * FROM "{table_name}" ORDER BY time ASC OFFSET {split_idx}',
                con=sync_engine, index_col='time'
            )
            df_full_oos.index = pd.to_datetime(df_full_oos.index)
            df_oos = df_full_oos.copy()

            df_full_oos = bot.researcher.generate_targets(df_full_oos)
            features = bot.researcher.features
            valid_cols = [c for c in features if c in df_full_oos.columns]
            if valid_cols:
                classes = list(getattr(target_model, 'classes_', [0, 1, 2]))
                proba_matrix = target_model.predict_proba(df_full_oos[valid_cols])
                
                idx_buy = classes.index(1) if 1 in classes else (1 if proba_matrix.shape[1] > 1 else None)
                idx_sell = classes.index(2) if 2 in classes else None
                
                p_buy = proba_matrix[:, idx_buy] if idx_buy is not None else np.zeros(len(df_oos))
                p_sell = proba_matrix[:, idx_sell] if idx_sell is not None else np.zeros(len(df_oos))
                
                df_oos['prob_buy'] = p_buy
                df_oos['prob_sell'] = p_sell
                df_oos['prob'] = np.maximum(p_buy, p_sell)
                df_oos['predicted_action'] = np.where(p_buy >= p_sell, "BUY", "SELL")
            else:
                df_oos['prob'] = np.random.uniform(0.5, 0.99, len(df_oos))
                df_oos['predicted_action'] = "BUY"
        else:
            df_oos = pd.read_sql(
                f'SELECT * FROM "{table_name}" ORDER BY time ASC OFFSET {split_idx}',
                con=sync_engine, index_col='time'
            )
            df_oos.index = pd.to_datetime(df_oos.index)
            np.random.seed(42 if mode_str == "normal" else 84)
            df_oos['prob'] = np.random.uniform(0.5, 0.99, len(df_oos))
            df_oos['predicted_action'] = "BUY"

        if df_oos.empty or len(df_oos) < 50:
            return {"status": "error", "message": "Data OOS tidak cukup.", "setup": None, "total": 0}

        processed = get_approved_setup_ids(mode=mode_str) | get_rejected_setup_ids(mode=mode_str) | get_ignored_setup_ids(mode=mode_str)
        high_prob = df_oos[df_oos['prob'] >= min_prob].copy()

        candidates = [
            idx for idx in high_prob.index
            if (idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, 'strftime') else str(idx)) not in processed
        ]
        total_pending = len(candidates)

        if total_pending == 0:
            return {"status": "done", "message": f"Semua setup OOS ({mode_str.upper()}) sudah dikurasi!", "setup": None, "total": 0, "current": 0}

        if offset >= total_pending:
            return {"status": "done", "message": "Sudah mencapai akhir antrian.", "setup": None, "total": total_pending, "current": offset}

        idx = candidates[offset]
        row = high_prob.loc[idx]
        setup_id = idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, 'strftime') else str(idx)

        # Resolusi Action (BUY vs SELL) secara akurat dari model multiclass atau close vs EMA 50
        pred_act = row.get('predicted_action', None)
        if pred_act in ["BUY", "SELL"]:
            action = pred_act
        else:
            dist = row.get('dist_Close_EMA50', None)
            if dist is None or pd.isna(dist):
                c_val = float(row.get('close', 0.0))
                ema_val = float(row.get('EMA_50', c_val))
                dist = c_val - ema_val
            action = "BUY" if dist >= 0 else "SELL"

        digits = 2 if ("XAU" in sym or "JPY" in sym) else 5
        atr = float(row.get('ATR_14', 0.0)) if 'ATR_14' in row.index else 0.0
        if pd.isna(atr) or atr <= 0:
            atr = 2.0 if "XAU" in sym else 0.0015
        price_val = float(row['close'])

        tp_multiplier = 2.0 if mode_str == "normal" else 5.0
        lookahead_candles = 100 if mode_str == "normal" else 300

        if action == "BUY":
            sl_val = round(price_val - atr, digits)
            tp_val = round(price_val + (atr * tp_multiplier), digits)
        else:
            sl_val = round(price_val + atr, digits)
            tp_val = round(price_val - (atr * tp_multiplier), digits)

        tf_resample = "15min" if atr >= 10.0 else "5min"
        tf_label = "M15" if atr >= 10.0 else "M5"

        pos_in_oos = df_oos.index.get_loc(idx)
        start = max(0, pos_in_oos - 150)
        end = min(len(df_oos), pos_in_oos + lookahead_candles + 100)

        slice_m1 = df_oos.iloc[start:end][['open', 'high', 'low', 'close']].copy()
        df_chart = slice_m1.resample(tf_resample).agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna()

        candles_list = [
            {"time": int(ts.timestamp()), "open": float(r['open']),
             "high": float(r['high']), "low": float(r['low']), "close": float(r['close'])}
            for ts, r in df_chart.iterrows()
        ]

        outcome = "UNKNOWN"
        post_m1 = df_oos.iloc[pos_in_oos + 1: pos_in_oos + lookahead_candles][['high', 'low']]
        for _, pc in post_m1.iterrows():
            if action == "BUY":
                if pc['low'] <= sl_val: outcome = "SL_HIT"; break
                if pc['high'] >= tp_val: outcome = "TP_HIT"; break
            else:
                if pc['high'] >= sl_val: outcome = "SL_HIT"; break
                if pc['low'] <= tp_val: outcome = "TP_HIT"; break

        logging.info(f"[RLHF Queue {mode_str.upper()}] Offset {offset}/{total_pending}: {setup_id} | {action} | Prob: {row['prob']:.2f} | Outcome: {outcome}")

        return {
            "status": "success",
            "mode": mode_str,
            "total": total_pending,
            "current": offset + 1,
            "setup": {
                "setup_id": setup_id,
                "mode": mode_str,
                "symbol": sym,
                "action": action,
                "price": price_val,
                "probability": float(row['prob']),
                "time": setup_id,
                "sl": sl_val,
                "tp": tp_val,
                "tp_multiplier": tp_multiplier,
                "outcome": outcome,
                "candles": candles_list,
                "entry_time": int(idx.timestamp()),
                "tf_label": tf_label
            }
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logging.error(f"Failed to fetch OOS review queue: {e}")
        return {"status": "error", "message": str(e), "setup": None, "total": 0}
