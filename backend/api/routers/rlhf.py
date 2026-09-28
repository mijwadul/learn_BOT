import logging
import asyncio
import time
import numpy as np
import pandas as pd
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from config import Config
from ..dependencies import bot

router = APIRouter(tags=["RLHF Human Feedback"])

# ─── In-Memory Cache untuk RLHF OOS Candidates ───────────────────────────────
# Menyimpan hasil prediksi OOS agar tidak recompute setiap request pagination.
# Key: (symbol, mode, min_prob_rounded)  |  TTL: 5 menit
_rlhf_cache: dict = {}
_RLHF_CACHE_TTL = 300       # detik (5 menit)
_MAX_OOS_ROWS   = 15_000    # Batas baris OOS yang dibaca ke RAM (cukup untuk kurasi)

def _get_rlhf_cache(key: tuple):
    entry = _rlhf_cache.get(key)
    if entry and (time.time() - entry["ts"]) < _RLHF_CACHE_TTL:
        return entry["data"]
    return None

def _set_rlhf_cache(key: tuple, data: dict):
    _rlhf_cache[key] = {"ts": time.time(), "data": data}

def _invalidate_rlhf_cache(symbol: str = None):
    """Hapus cache saat ada feedback baru agar kandidat diperbarui."""
    keys_to_del = [k for k in _rlhf_cache if symbol is None or k[0] == symbol.upper()]
    for k in keys_to_del:
        _rlhf_cache.pop(k, None)
# ─────────────────────────────────────────────────────────────────────────────

class RLHFRequest(BaseModel):
    setup_id: str
    decision: str # "approve", "reject", or "ignore"
    symbol: Optional[str] = "XAUUSD"
    action_type: Optional[str] = "BUY"
    probability: Optional[float] = 0.0
    notes: Optional[str] = ""
    mode: Optional[str] = "normal"

class RLHFBatchItem(BaseModel):
    setup_id: str
    decision: str # "approve", "reject", or "ignore"
    symbol: Optional[str] = "XAUUSD"
    action_type: Optional[str] = "BUY"
    probability: Optional[float] = 0.0
    notes: Optional[str] = ""
    mode: Optional[str] = "normal"

class RLHFBatchRequest(BaseModel):
    items: list[RLHFBatchItem]

@router.post("/api/rlhf/feedback")
async def submit_rlhf(req: RLHFRequest):
    try:
        from database import save_approved_setup, save_rejected_setup, save_ignored_setup
        mode_val = req.mode.lower() if req.mode else "normal"
        sym = (req.symbol or "XAUUSD").upper()
        logging.info(f"Menerima RLHF Feedback: {req.decision.upper()} [{mode_val.upper()}] ({sym}) untuk {req.setup_id}")

        if req.decision == "approve":
            await asyncio.to_thread(save_approved_setup, req.setup_id, sym, req.action_type, req.probability, req.notes, mode=mode_val)
        elif req.decision == "reject":
            await asyncio.to_thread(save_rejected_setup, req.setup_id, sym, req.action_type, req.probability, req.notes, mode=mode_val)
        elif req.decision == "ignore":
            await asyncio.to_thread(save_ignored_setup, req.setup_id, sym, req.action_type, req.probability, req.notes, mode=mode_val)
        else:
            return {"status": "error", "message": f"Decision tidak valid: {req.decision}. Gunakan approve/reject/ignore."}

        # Invalidasi cache agar kandidat diperbarui di request berikutnya
        _invalidate_rlhf_cache(sym)
        return {"status": "success", "message": f"Setup {req.setup_id} marked as {req.decision} ({mode_val} - {sym})."}
    except Exception as e:
        logging.error(f"RLHF error: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/api/rlhf/feedback-batch")
async def submit_rlhf_batch(req: RLHFBatchRequest):
    try:
        from database import save_approved_setup, save_rejected_setup, save_ignored_setup
        saved_count = 0
        affected_symbols: set = set()
        for item in req.items:
            mode_val = item.mode.lower() if item.mode else "normal"
            sym = (item.symbol or "XAUUSD").upper()
            if item.decision == "approve":
                await asyncio.to_thread(save_approved_setup, item.setup_id, sym, item.action_type, item.probability, item.notes, mode=mode_val)
                saved_count += 1
            elif item.decision == "reject":
                await asyncio.to_thread(save_rejected_setup, item.setup_id, sym, item.action_type, item.probability, item.notes, mode=mode_val)
                saved_count += 1
            elif item.decision == "ignore":
                await asyncio.to_thread(save_ignored_setup, item.setup_id, sym, item.action_type, item.probability, item.notes, mode=mode_val)
                saved_count += 1
            affected_symbols.add(sym)

        # Invalidasi cache untuk semua pair yang ada feedback barunya
        for s in affected_symbols:
            _invalidate_rlhf_cache(s)
        return {"status": "success", "saved_count": saved_count, "message": f"Berhasil menyimpan {saved_count} keputusan feedback."}
    except Exception as e:
        logging.error(f"RLHF batch error: {e}")
        return {"status": "error", "message": str(e)}

def _build_candles_with_bbma(df_slice: pd.DataFrame, timeframe: str = "M5") -> tuple[list, str]:
    from utils.indicators import calculate_bbma
    tf = (timeframe or "M5").upper()
    tf_resample_map = {
        "M1": "1min",
        "M5": "5min",
        "M15": "15min",
        "M30": "30min",
        "H1": "60min"
    }
    if tf not in tf_resample_map:
        tf = "M5"
    tf_rule = tf_resample_map[tf]

    if tf == "M1":
        df_chart = df_slice[['open', 'high', 'low', 'close']].copy()
    else:
        df_chart = df_slice[['open', 'high', 'low', 'close']].resample(tf_rule).agg(
            {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        ).dropna()

    df_chart = calculate_bbma(df_chart)

    candles_list = []
    for ts, r in df_chart.iterrows():
        candles_list.append({
            "time": int(ts.timestamp()),
            "open": float(r['open']),
            "high": float(r['high']),
            "low": float(r['low']),
            "close": float(r['close']),
            "sma_20": round(float(r['SMA_20']), 4) if ('SMA_20' in r and not pd.isna(r['SMA_20'])) else None,
            "bb_upper": round(float(r['BB_Upper']), 4) if ('BB_Upper' in r and not pd.isna(r['BB_Upper'])) else None,
            "bb_lower": round(float(r['BB_Lower']), 4) if ('BB_Lower' in r and not pd.isna(r['BB_Lower'])) else None,
            "ema_50": round(float(r['EMA_50']), 4) if ('EMA_50' in r and not pd.isna(r['EMA_50'])) else None,
            "lwma_5_h": round(float(r['LWMA_5_High']), 4) if ('LWMA_5_High' in r and not pd.isna(r['LWMA_5_High'])) else None,
            "lwma_10_h": round(float(r['LWMA_10_High']), 4) if ('LWMA_10_High' in r and not pd.isna(r['LWMA_10_High'])) else None,
            "lwma_5_l": round(float(r['LWMA_5_Low']), 4) if ('LWMA_5_Low' in r and not pd.isna(r['LWMA_5_Low'])) else None,
            "lwma_10_l": round(float(r['LWMA_10_Low']), 4) if ('LWMA_10_Low' in r and not pd.isna(r['LWMA_10_Low'])) else None,
        })
    return candles_list, tf

@router.get("/api/rlhf/chart")
async def get_rlhf_chart(
    setup_id: str,
    symbol: Optional[str] = "XAUUSD",
    timeframe: str = "M5",
    mode: str = "normal"
):
    """
    Mengambil data candlestick dan seluruh indikator BBMA (Mid BB, Upper/Lower BB, EMA 50, LWMA 5/10 H/L)
    secara dinamis untuk setup tertentu pada timeframe yang diminta (M1, M5, M15, M30, H1).
    """
    def _fetch():
        from database import sync_engine, get_market_table_name
        sym = (symbol or getattr(bot.researcher, "symbol", "XAUUSD") or "XAUUSD").upper()
        table_name = get_market_table_name(sym)

        try:
            target_ts = pd.to_datetime(setup_id)
        except Exception:
            return {"status": "error", "message": "Format setup_id waktu tidak valid."}

        tf = (timeframe or "M5").upper()
        lookback_map = {"M1": 200, "M5": 600, "M15": 1500, "M30": 3000, "H1": 6000}
        lookahead_map = {"M1": 200, "M5": 600, "M15": 1200, "M30": 2400, "H1": 4000}
        lb = lookback_map.get(tf, 600)
        la = lookahead_map.get(tf, 600)

        start_time = target_ts - pd.Timedelta(minutes=lb)
        end_time = target_ts + pd.Timedelta(minutes=la)

        query = f'SELECT "time", open, high, low, close FROM "{table_name}" WHERE "time" >= \'{start_time}\' AND "time" <= \'{end_time}\' ORDER BY "time" ASC'
        try:
            df = pd.read_sql(query, con=sync_engine, index_col='time')
            df.index = pd.to_datetime(df.index)
        except Exception as e:
            if sym == "XAUUSD":
                try:
                    query = f'SELECT "time", open, high, low, close FROM "market_data_merged" WHERE "time" >= \'{start_time}\' AND "time" <= \'{end_time}\' ORDER BY "time" ASC'
                    df = pd.read_sql(query, con=sync_engine, index_col='time')
                    df.index = pd.to_datetime(df.index)
                except Exception:
                    return {"status": "error", "message": f"Gagal membaca candle dari DB: {e}"}
            else:
                return {"status": "error", "message": f"Gagal membaca candle dari DB: {e}"}

        if df.empty:
            return {"status": "error", "message": "Data candle tidak ditemukan pada rentang waktu ini."}

        candles_list, actual_tf = _build_candles_with_bbma(df, tf)

        return {
            "status": "success",
            "setup_id": setup_id,
            "symbol": sym,
            "timeframe": actual_tf,
            "entry_time": int(target_ts.timestamp()),
            "candles": candles_list
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logging.error(f"Gagal memuat chart setup: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/api/rlhf/setups")
async def get_rlhf_setups(
    min_prob: float = 0.65,
    page: int = 1,
    page_size: int = 10,
    offset: Optional[int] = None,
    mode: str = "normal",
    symbol: Optional[str] = None,
    timeframe: str = "M5"
):
    """
    Review Queue: Kembalikan 10 setup OOS per halaman khusus untuk pair terpilih.
    Mendukung paginasi batch 10 data, statistik kurasi (approved/rejected/ignored/total),
    dan candle interaktif dengan indikator BBMA lengkap.
    """
    def _fetch():
        from database import (
            sync_engine, 
            get_approved_setup_ids, 
            get_rejected_setup_ids, 
            get_ignored_setup_ids, 
            get_market_table_name,
            get_rlhf_curation_stats
        )
        mode_str = mode.lower() if mode else "normal"
        sym = (symbol or getattr(bot.researcher, "symbol", "XAUUSD") or "XAUUSD").upper()
        table_name = get_market_table_name(sym)

        # Sinkronkan model researcher bila belum sesuai dengan pair terpilih
        if hasattr(bot, 'researcher') and bot.researcher is not None:
            if getattr(bot.researcher, "symbol", "") != sym:
                bot.researcher.set_symbol(sym)

        # Ambil statistik kurasi saat ini untuk pair & mode ini
        stats = get_rlhf_curation_stats(symbol=sym, mode=mode_str)

        # Cek ketersediaan tabel di DB
        try:
            query_count = f'SELECT COUNT(*) FROM "{table_name}"'
            total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
        except Exception:
            table_name = "market_data_merged" if sym == "XAUUSD" else table_name
            try:
                query_count = f'SELECT COUNT(*) FROM "{table_name}"'
                total_rows = pd.read_sql(query_count, con=sync_engine).iloc[0, 0]
            except Exception:
                total_rows = 0

        if total_rows < 100:
            return {
                "status": "error",
                "message": f"Database {sym} belum memiliki cukup data candle ({total_rows} baris). Jalankan Force Backfill MT5 terlebih dahulu.",
                "setup": None,
                "setups": [],
                "total": 0,
                "total_pending": 0,
                "stats": stats
            }

        split_idx = int(total_rows * 0.8)

        # ── Cache check: jika sudah ada hasil prediksi, langsung pakai ────────
        min_prob_key = round(min_prob, 2)
        cache_key = (sym, mode_str, min_prob_key)
        cached = _get_rlhf_cache(cache_key)
        if cached is not None:
            logging.info(f"[RLHF Cache HIT] {sym} {mode_str} prob>={min_prob_key}")
            df_oos        = cached["df_oos"]
            candidates    = cached["candidates"]
            processed_set = cached["processed"]
            high_prob     = cached.get("high_prob", df_oos[df_oos['prob'] >= min_prob])
            # Update processed set dengan feedback terbaru (bisa berubah sejak cache)
            fresh_processed = (
                get_approved_setup_ids(mode=mode_str, symbol=sym) |
                get_rejected_setup_ids(mode=mode_str, symbol=sym) |
                get_ignored_setup_ids(mode=mode_str, symbol=sym)
            )
            if fresh_processed != processed_set:
                # Ada feedback baru → filter ulang candidates dari df_oos
                high_prob  = df_oos[df_oos['prob'] >= min_prob]
                candidates = [
                    idx for idx in high_prob.index
                    if (idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, 'strftime') else str(idx))
                    not in fresh_processed
                ]
                cached["candidates"] = candidates
                cached["processed"]  = fresh_processed
                cached["high_prob"]  = high_prob
        else:
            logging.info(f"[RLHF Cache MISS] {sym} {mode_str} — memulai komputasi OOS (max {_MAX_OOS_ROWS} baris)...")
            target_model = bot.researcher.model_normal if mode_str == "normal" else bot.researcher.model_runner
            if target_model is not None:
                # ── Baca hanya N baris OOS terbaru (KRITIS: bukan semua baris!) ──
                oos_limit = min(_MAX_OOS_ROWS, max(0, total_rows - split_idx))
                df_full_oos = pd.read_sql(
                    f'SELECT * FROM "{table_name}" ORDER BY time DESC LIMIT {oos_limit}',
                    con=sync_engine, index_col='time'
                )
                df_full_oos.index = pd.to_datetime(df_full_oos.index)
                df_full_oos = df_full_oos.sort_index()  # kembalikan urutan ASC
                df_oos = df_full_oos.copy()

                df_full_oos = bot.researcher.generate_targets(df_full_oos)
                df_full_oos = bot.researcher.add_normalized_features(df_full_oos)
                features = []
                if hasattr(target_model, 'feature_name_') and target_model.feature_name_ is not None:
                    features = list(target_model.feature_name_)
                elif hasattr(target_model, 'booster_') and hasattr(target_model.booster_, 'feature_name'):
                    features = list(target_model.booster_.feature_name())
                if not features:
                    features = bot.researcher.get_model_features(target_model, mode=mode_str)

                if features:
                    classes = list(getattr(target_model, 'classes_', [0, 1]))
                    X_oos = df_full_oos.reindex(columns=features, fill_value=0.0).copy()
                    for c in features:
                        if not (pd.api.types.is_numeric_dtype(X_oos[c]) or pd.api.types.is_bool_dtype(X_oos[c])):
                            X_oos[c] = pd.to_numeric(X_oos[c], errors='coerce').fillna(0.0)
                    proba_matrix = target_model.predict_proba(X_oos)
                
                    if len(classes) == 2 or proba_matrix.shape[1] == 2:
                        idx_win = classes.index(1) if 1 in classes else 1
                        p_win = proba_matrix[:, idx_win] if proba_matrix.shape[1] > idx_win else proba_matrix[:, -1]
                        open_c = df_oos['open'].values if 'open' in df_oos.columns else df_oos['close'].values
                        close_c = df_oos['close'].values
                        is_bull = close_c >= open_c
                        p_buy = np.where(is_bull, p_win, 0.0)
                        p_sell = np.where(~is_bull, p_win, 0.0)
                        df_oos['prob_buy'] = p_buy
                        df_oos['prob_sell'] = p_sell
                        df_oos['prob'] = p_win
                        df_oos['predicted_action'] = np.where(is_bull, "BUY", "SELL")
                    else:
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
                # Tidak ada model — baca saja baris OOS terbatas untuk preview
                oos_limit = min(_MAX_OOS_ROWS, max(0, total_rows - split_idx))
                df_oos = pd.read_sql(
                    f'SELECT * FROM "{table_name}" ORDER BY time DESC LIMIT {oos_limit}',
                    con=sync_engine, index_col='time'
                )
                df_oos.index = pd.to_datetime(df_oos.index)
                df_oos = df_oos.sort_index()
                np.random.seed(42 if mode_str == "normal" else 84)
                df_oos['prob'] = np.random.uniform(0.5, 0.99, len(df_oos))
                df_oos['predicted_action'] = "BUY"

            if df_oos.empty or len(df_oos) < 50:
                return {
                    "status": "error",
                    "message": f"Data OOS untuk {sym} tidak mencukupi.",
                    "setup": None,
                    "setups": [],
                    "total": 0,
                    "total_pending": 0,
                    "stats": stats
                }

            # Filter eksklusif untuk pair bersangkutan
            processed = (
                get_approved_setup_ids(mode=mode_str, symbol=sym) |
                get_rejected_setup_ids(mode=mode_str, symbol=sym) |
                get_ignored_setup_ids(mode=mode_str, symbol=sym)
            )
            high_prob  = df_oos[df_oos['prob'] >= min_prob].copy()
            candidates = [
                idx for idx in high_prob.index
                if (idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, 'strftime') else str(idx)) not in processed
            ]

            # ── Simpan ke cache ───────────────────────────────────────────────
            _set_rlhf_cache(cache_key, {
                "df_oos": df_oos,
                "high_prob": high_prob,
                "candidates": candidates,
                "processed": processed
            })
            logging.info(f"[RLHF Cache SET] {sym} {mode_str} — {len(candidates)} kandidat dari {len(df_oos)} baris OOS")
        total_pending = len(candidates)

        if total_pending == 0:
            return {
                "status": "done",
                "message": f"Seluruh setup OOS {sym} ({mode_str.upper()}) dengan probabilitas >= {min_prob*100:.0f}% sudah selesai dikurasi!",
                "setup": None,
                "setups": [],
                "total": 0,
                "total_pending": 0,
                "current": 0,
                "page": 1,
                "page_size": page_size,
                "total_pages": 0,
                "symbol": sym,
                "stats": stats
            }

        # Paginasi 10 data per halaman
        p_size = max(1, page_size)
        cur_page = page
        if offset is not None and offset > 0:
            cur_page = (offset // p_size) + 1
        cur_page = max(1, cur_page)
        
        total_pages = max(1, (total_pending + p_size - 1) // p_size)
        if cur_page > total_pages:
            cur_page = total_pages

        start_idx = (cur_page - 1) * p_size
        end_idx = min(total_pending, start_idx + p_size)
        page_indices = candidates[start_idx:end_idx]

        digits = 2 if ("XAU" in sym or "JPY" in sym or "OIL" in sym) else 5
        tp_multiplier = 2.0 if mode_str == "normal" else 5.0
        lookahead_candles = 100 if mode_str == "normal" else 300

        setups_list = []
        for p_idx in page_indices:
            if 'high_prob' in locals() and p_idx in high_prob.index:
                row_p = high_prob.loc[p_idx]
            else:
                row_p = df_oos.loc[p_idx]
            if isinstance(row_p, pd.DataFrame):
                row_p = row_p.iloc[-1]
            s_id = p_idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(p_idx, 'strftime') else str(p_idx)

            p_act = row_p.get('predicted_action', None)
            if p_act in ["BUY", "SELL"]:
                act = p_act
            else:
                dist = row_p.get('dist_Close_EMA50', None)
                if dist is None or pd.isna(dist):
                    c_v = float(row_p.get('close', 0.0))
                    e_v = float(row_p.get('EMA_50', c_v))
                    dist = c_v - e_v
                act = "BUY" if dist >= 0 else "SELL"

            atr_val = float(row_p.get('ATR_14', 0.0)) if 'ATR_14' in row_p.index else 0.0
            if pd.isna(atr_val) or atr_val <= 0:
                atr_val = 2.0 if ("XAU" in sym or "OIL" in sym) else 0.0015
            p_val = float(row_p['close'])

            if act == "BUY":
                sl_p = round(p_val - atr_val, digits)
                tp_p = round(p_val + (atr_val * tp_multiplier), digits)
            else:
                sl_p = round(p_val + atr_val, digits)
                tp_p = round(p_val - (atr_val * tp_multiplier), digits)

            # Hitung outcome historis
            p_pos = df_oos.index.get_loc(p_idx)
            p_outcome = "UNKNOWN"
            p_post = df_oos.iloc[p_pos + 1: p_pos + lookahead_candles][['high', 'low']]
            for _, pc in p_post.iterrows():
                if act == "BUY":
                    if pc['low'] <= sl_p: p_outcome = "SL_HIT"; break
                    if pc['high'] >= tp_p: p_outcome = "TP_HIT"; break
                else:
                    if pc['high'] >= sl_p: p_outcome = "SL_HIT"; break
                    if pc['low'] <= tp_p: p_outcome = "TP_HIT"; break

            setups_list.append({
                "setup_id": s_id,
                "mode": mode_str,
                "symbol": sym,
                "action": act,
                "price": p_val,
                "probability": float(row_p['prob']),
                "time": s_id,
                "sl": sl_p,
                "tp": tp_p,
                "tp_multiplier": tp_multiplier,
                "outcome": p_outcome,
                "entry_time": int(p_idx.timestamp()),
            })

        # Untuk setup aktif utama (setup pertama di halaman ini), buat data candle & BBMA
        active_setup = None
        if setups_list:
            first_idx = page_indices[0]
            first_setup = setups_list[0]
            first_pos = df_oos.index.get_loc(first_idx)
            
            tf_to_use = (timeframe or "M5").upper()
            lookback_m1 = 500
            lookahead_m1 = 500
            if tf_to_use in ["M15", "M30"]:
                lookback_m1 = 1500
                lookahead_m1 = 1000
            elif tf_to_use == "H1":
                lookback_m1 = 3500
                lookahead_m1 = 2000

            s_start = max(0, first_pos - lookback_m1)
            s_end = min(len(df_oos), first_pos + lookahead_m1)
            slice_data = df_oos.iloc[s_start:s_end]
            candles_res, actual_tf = _build_candles_with_bbma(slice_data, tf_to_use)

            active_setup = {
                **first_setup,
                "candles": candles_res,
                "tf_label": actual_tf
            }

        logging.info(f"[RLHF Queue {mode_str.upper()} - {sym}] Halaman {cur_page}/{total_pages} ({len(setups_list)} data). Total harus dikurasi: {total_pending}")

        return {
            "status": "success",
            "mode": mode_str,
            "symbol": sym,
            "total": total_pending,
            "total_pending": total_pending,
            "page": cur_page,
            "page_size": p_size,
            "total_pages": total_pages,
            "current": start_idx + 1,
            "stats": stats,
            "setups": setups_list,
            "setup": active_setup
        }

    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logging.error(f"Failed to fetch OOS review queue: {e}")
        return {
            "status": "error", 
            "message": str(e), 
            "setup": None, 
            "setups": [],
            "total": 0, 
            "total_pending": 0
        }
