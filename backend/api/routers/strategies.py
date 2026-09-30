import logging
import threading
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

from ..dependencies import bot

router = APIRouter(tags=["Strategies & Training"])

from typing import Optional
import os
import json
from pathlib import Path
from agents.research.explainer import extract_feature_importance
from agents.research.model_manager import ModelManager, sanitize_json_floats

class ModeRequest(BaseModel):
    mode: str
    symbol: Optional[str] = "XAUUSD"

class ToggleBrainRequest(BaseModel):
    mode: str = "all" # 'normal', 'runner', or 'all'
    active: bool = True
    symbol: Optional[str] = "XAUUSD"

class ToggleAllBrainsRequest(BaseModel):
    active: bool = True
    symbol: Optional[str] = "XAUUSD"

class TrainRequest(BaseModel):
    type: str # 'full' or 'incremental'
    mode: str # 'normal' or 'runner'
    symbol: Optional[str] = "XAUUSD"

class ResetModelRequest(BaseModel):
    symbol: Optional[str] = "XAUUSD"

class ConfirmSaveModelRequest(BaseModel):
    symbol: Optional[str] = "XAUUSD"
    mode: str = "normal" # "normal" or "runner"
    action: str = "save" # "save" or "discard"

class MicroTrainRequest(BaseModel):
    mode: str = "all" # "normal", "runner", or "all"
    symbol: Optional[str] = "XAUUSD"

class QueueTaskItem(BaseModel):
    id: Optional[str] = None
    symbol: str = "XAUUSD"
    mode: str # "normal" or "runner"
    type: str # "full" or "incremental"

class QueueTrainRequest(BaseModel):
    tasks: list[QueueTaskItem]
    post_completion_action: str = "idle" # "idle" or "force_live"
    auto_apply: bool = True # Automatically apply model to live if passed OOS / completed

@router.get("/api/strategies/status")
async def get_strategy_model_status(symbol: Optional[str] = "XAUUSD"):
    """Mengembalikan status model dan akurasi khusus untuk pair tertentu dari disk/memory."""
    sym = (symbol or "XAUUSD").upper()
    meta_path = Path("models") / sym / "models_metadata.json"
    norm_pkl = Path("models") / sym / "model_normal.pkl"
    run_pkl = Path("models") / sym / "model_runner.pkl"

    meta = {}
    if meta_path.exists():
        try:
            with open(meta_path, "r") as f:
                meta = json.load(f)
        except Exception:
            pass

    # Jika sedang melatih pair yang sama di in-memory bot
    is_same_pair = (getattr(bot.researcher, "symbol", "XAUUSD").upper() == sym)
    
    norm_meta = meta.get("normal", {})
    run_meta = meta.get("runner", {})

    last_acc_normal = bot.researcher.last_accuracy_normal if is_same_pair else float(norm_meta.get("last_accuracy", 0.0))
    last_acc_runner = bot.researcher.last_accuracy_runner if is_same_pair else float(run_meta.get("last_accuracy", 0.0))
    last_train_normal = bot.researcher.last_trained_normal if is_same_pair else norm_meta.get("last_trained_at")
    last_train_runner = bot.researcher.last_trained_runner if is_same_pair else run_meta.get("last_trained_at")

    normal_trained = (bot.researcher.model_normal is not None if is_same_pair else (norm_pkl.exists() or norm_meta.get("trained", False)))
    runner_trained = (bot.researcher.model_runner is not None if is_same_pair else (run_pkl.exists() or run_meta.get("trained", False)))

    is_normal_active = bot.supervisor.is_normal_valid(sym)
    is_runner_active = bot.supervisor.is_runner_valid(sym)

    # Deteksi pending model yang menunggu konfirmasi penyimpanan dari user
    pending_models = {}
    for m in ["normal", "runner"]:
        p_info = None
        if is_same_pair and hasattr(bot.researcher, "pending_training") and m in bot.researcher.pending_training:
            p_info = bot.researcher.pending_training[m].get("info")
        if not p_info:
            p_info = ModelManager.get_pending_info(sym, m)
        if p_info:
            pending_models[m] = p_info

    res = {
        "status": "success",
        "symbol": sym,
        "is_normal_active": is_normal_active,
        "is_runner_active": is_runner_active,
        "all_brains_active": is_normal_active and is_runner_active,
        "pending_models": pending_models,
        "models_status": {
            "normal": {
                "trained": normal_trained,
                "is_active": is_normal_active,
                "status": "LIVE/LAYAK" if is_normal_active else "IDLE/QUARANTINE",
                "is_training": bot.researcher.is_training_normal if is_same_pair else False,
                "last_accuracy": last_acc_normal,
                "last_trained": last_train_normal,
                "has_pending": "normal" in pending_models
            },
            "runner": {
                "trained": runner_trained,
                "is_active": is_runner_active,
                "status": "LIVE/LAYAK" if is_runner_active else "IDLE/QUARANTINE",
                "is_training": bot.researcher.is_training_runner if is_same_pair else False,
                "last_accuracy": last_acc_runner,
                "last_trained": last_train_runner,
                "has_pending": "runner" in pending_models
            }
        }
    }
    return sanitize_json_floats(res)

@router.post("/api/strategies/toggle-brain")
async def toggle_brain(req: ToggleBrainRequest):
    """Mengaktifkan atau menonaktifkan salah satu otak ('normal', 'runner') atau semua ('all') untuk pair spesifik."""
    target = (req.mode or "all").lower()
    sym = (req.symbol or "XAUUSD").upper()
    bot.supervisor.set_brain_active(target, req.active, symbol=sym)
    if req.active and bot.supervisor.state == 'live':
        bot.is_live = True
    return {
        "status": "success",
        "symbol": sym,
        "mode": target,
        "active": req.active,
        "is_normal_active": bot.supervisor.is_normal_valid(sym),
        "is_runner_active": bot.supervisor.is_runner_valid(sym),
        "all_brains_active": bot.supervisor.is_normal_valid(sym) and bot.supervisor.is_runner_valid(sym),
        "state": bot.supervisor.state,
        "message": f"Otak {target.upper()} ({sym}) berhasil {'DIAKTIFKAN (LIVE)' if req.active else 'DINONAKTIFKAN (QUARANTINE)'}."
    }

@router.post("/api/strategies/toggle-all-brains")
async def toggle_all_brains(req: ToggleAllBrainsRequest):
    """Mengaktifkan atau menonaktifkan SEMUA otak sekaligus (Scalp + Runner) untuk pair spesifik."""
    sym = (req.symbol or "XAUUSD").upper()
    bot.supervisor.set_brain_active("all", req.active, symbol=sym)
    if req.active and bot.supervisor.state == 'live':
        bot.is_live = True
    return {
        "status": "success",
        "symbol": sym,
        "active": req.active,
        "is_normal_active": bot.supervisor.is_normal_valid(sym),
        "is_runner_active": bot.supervisor.is_runner_valid(sym),
        "all_brains_active": req.active,
        "state": bot.supervisor.state,
        "message": f"Semua otak ({sym} Scalp & Runner) berhasil {'DIAKTIFKAN (LIVE)' if req.active else 'DINONAKTIFKAN (QUARANTINE)'}."
    }

@router.post("/api/strategies/force_live")
async def force_live(req: ModeRequest):
    sym = (getattr(req, "symbol", None) or "XAUUSD").upper()
    bot.supervisor.force_live_mode(req.mode, symbol=sym)
    if bot.supervisor.state == 'live':
        bot.is_live = True
    return {
        "status": "success",
        "symbol": sym,
        "mode": req.mode,
        "action": "force_live",
        "state": bot.supervisor.state,
        "is_normal_active": bot.supervisor.is_normal_valid(sym),
        "is_runner_active": bot.supervisor.is_runner_valid(sym)
    }

@router.post("/api/strategies/quarantine")
async def quarantine(req: ModeRequest):
    sym = (getattr(req, "symbol", None) or "XAUUSD").upper()
    bot.supervisor.isolate_quarantine(req.mode, symbol=sym)
    return {
        "status": "success",
        "symbol": sym,
        "mode": req.mode,
        "action": "quarantine",
        "state": bot.supervisor.state,
        "is_normal_active": bot.supervisor.is_normal_valid(sym),
        "is_runner_active": bot.supervisor.is_runner_valid(sym)
    }

@router.post("/api/strategies/train")
async def train_model(req: TrainRequest):
    target_symbol = (req.symbol or "XAUUSD").upper()

    def _train_task():
        try:
            logging.info(f"Memulai pelatihan AI ({req.type}) untuk {target_symbol} - {req.mode} Mode...")

            # Sinkronkan target symbol ke miner dan researcher
            bot.data_miner.set_symbol(target_symbol)
            bot.researcher.set_symbol(target_symbol)

            total_chunks, data_generator = bot.data_miner.load_train_chunks(chunk_size=100000, mode=req.mode, symbol=target_symbol)
            if total_chunks == 0 or data_generator is None:
                logging.warning(f"⚠️ Training dibatalkan: Database {bot.data_miner.table_name} kosong. Jalankan Force Backfill MT5 terlebih dahulu.")
                return
                
            total_test_chunks, test_generator = bot.data_miner.load_test_chunks(chunk_size=100000, symbol=target_symbol)

            bot.researcher._current_train_type = req.type

            if req.type == 'full':
                bot.researcher.features = []
                logging.info(f"[FULL TRAIN - {target_symbol}] Mode {req.mode.upper()} akan dilatih ulang dari awal dengan Optuna...")

            if req.mode == 'normal':
                bot.researcher.is_training_normal = True
                try:
                    result = bot.researcher.train_normal_mode(data_generator, total_chunks=total_chunks, data_miner=bot.data_miner, train_type=req.type)
                    logging.info(f"✅ Pelatihan Normal ({req.type}) selesai. Hasil tersimpan sebagai PENDING model menunggu konfirmasi dialog.")
                finally:
                    bot.researcher.is_training_normal = False
            elif req.mode == 'runner':
                bot.researcher.is_training_runner = True
                try:
                    result = bot.researcher.train_runner_mode(data_generator, total_chunks=total_chunks, data_miner=bot.data_miner, train_type=req.type)
                    logging.info(f"✅ Pelatihan Runner ({req.type}) selesai. Hasil tersimpan sebagai PENDING model menunggu konfirmasi dialog.")
                finally:
                    bot.researcher.is_training_runner = False

            logging.info(f"✅ Pelatihan AI ({req.type}) untuk {req.mode} Mode ({target_symbol}) selesai diproses.")
        except Exception as e:
            import traceback
            logging.error(f"Training failed: {e}")
            logging.error(traceback.format_exc())

    threading.Thread(target=_train_task, daemon=True).start()
    return {"status": "success", "message": f"{req.type.capitalize()} Training {req.mode} mode started in background. Cek Logs untuk progress."}

@router.post("/api/strategies/micro-train")
async def trigger_micro_train(req: MicroTrainRequest = None):
    """Memicu Online Learning Micro-Retrain secara on-demand / manual terisolasi per pair."""
    target_mode = req.mode.lower() if req and req.mode else "all"
    target_symbol = (req.symbol if req and req.symbol else getattr(bot.researcher, "symbol", "XAUUSD")).upper()

    def _micro_task():
        try:
            logging.info(f"[API MICRO-TRAIN] Memulai Micro-Retrain on-demand untuk {target_symbol} - mode: {target_mode.upper()}...")
            if bot.data_miner:
                bot.data_miner.set_symbol(target_symbol)
                if bot.mt5_connected:
                    try:
                        logging.info(f"[API MICRO-TRAIN] Sinkronisasi candle MT5 terbaru ({target_symbol}) ke database...")
                        bot.data_miner.sync_latest_data()
                    except Exception as e_sync:
                        logging.warning(f"[API MICRO-TRAIN] Gagal auto-sync MT5: {e_sync}")

            df_recent = bot.data_miner.load_recent_micro_chunk(n_candles=3000)
            if df_recent is None or df_recent.empty:
                logging.warning(f"[API MICRO-TRAIN] Data candle recent {target_symbol} kosong di database.")
                return

            if bot.researcher:
                bot.researcher.set_symbol(target_symbol)
                if target_mode in ["normal", "all"] and bot.researcher.model_normal is not None:
                    fb_normal = bot.data_miner.load_live_decision_chunk(mode="normal", symbol=target_symbol)
                    bot.researcher.micro_retrain("normal", df_recent, fb_normal)

                if target_mode in ["runner", "all"] and bot.researcher.model_runner is not None:
                    fb_runner = bot.data_miner.load_live_decision_chunk(mode="runner", symbol=target_symbol)
                    bot.researcher.micro_retrain("runner", df_recent, fb_runner)

            bot.executor.last_micro_retrain_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"✅ [API MICRO-TRAIN] Micro-Retrain {target_symbol} selesai pada {bot.executor.last_micro_retrain_time}.")
        except Exception as e:
            logging.error(f"[API MICRO-TRAIN] Gagal: {e}")

    threading.Thread(target=_micro_task, daemon=True).start()
    return {"status": "success", "message": f"Online Micro-Retrain ({target_symbol} {target_mode.upper()}) started in background. Cek Logs untuk progress."}

class ValidateRequest(BaseModel):
    mode: str = "normal" # "normal" or "runner"
    symbol: Optional[str] = "XAUUSD"

@router.post("/api/strategies/validate")
async def trigger_validate(req: ValidateRequest = None):
    """Menjalankan validasi OOS langsung pada model tersimpan dengan parameter terbaru tanpa retraining."""
    target_mode = req.mode.lower() if req and req.mode else "normal"
    target_symbol = (req.symbol if req and req.symbol else getattr(bot.researcher, "symbol", "XAUUSD")).upper()
    def _validate_task():
        try:
            if bot.data_miner:
                bot.data_miner.set_symbol(target_symbol)
            if bot.researcher:
                bot.researcher.set_symbol(target_symbol)
            total_test_chunks, test_generator = bot.data_miner.load_test_chunks(chunk_size=100000, symbol=target_symbol)
            if not test_generator or total_test_chunks == 0:
                logging.warning(f"⚠️ [VALIDATE] Data OOS kosong untuk {target_symbol} - {target_mode}.")
                return
            logging.info(f"Memulai validasi OOS on-demand untuk {target_symbol} - {target_mode.upper()}...")
            accuracy = bot.gatekeeper.validate_model(target_mode, test_generator, total_test_chunks)
            if target_mode == 'normal':
                bot.researcher.last_accuracy_normal = float(accuracy)
                bot.researcher.last_trained_normal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                bot.researcher.save_metadata()
                if accuracy >= 0.50:
                    bot.supervisor.set_model_validity(True, bot.supervisor.is_runner_valid())
                    logging.info(f"✅ Model Normal ({target_symbol}) lulus validasi (Win Rate: {accuracy*100:.2f}% >= 50%). Supervisor Normal Mode = VALID.")
                else:
                    bot.supervisor.set_model_validity(False, bot.supervisor.is_runner_valid())
                    logging.warning(f"❌ Model Normal ({target_symbol}) gagal validasi (Win Rate: {accuracy*100:.2f}% < 50%). Supervisor Normal Mode = QUARANTINE.")
            elif target_mode == 'runner':
                bot.researcher.last_accuracy_runner = float(accuracy)
                bot.researcher.last_trained_runner = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                bot.researcher.save_metadata()
                RUNNER_MIN_WIN_RATE = 0.25
                if accuracy >= RUNNER_MIN_WIN_RATE:
                    bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(), True)
                    logging.info(f"✅ Model Runner ({target_symbol}) lulus validasi (Win Rate: {accuracy*100:.2f}% >= {RUNNER_MIN_WIN_RATE*100:.0f}% pada RR 1:5). Supervisor Runner Mode = VALID.")
                else:
                    bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(), False)
                    logging.warning(f"❌ Model Runner ({target_symbol}) gagal validasi (Win Rate: {accuracy*100:.2f}% < {RUNNER_MIN_WIN_RATE*100:.0f}%). Supervisor Runner Mode = QUARANTINE.")
        except Exception as e:
            logging.error(f"[VALIDATE] Gagal: {e}")

    threading.Thread(target=_validate_task, daemon=True).start()
    return {"status": "success", "message": f"Validasi OOS {target_symbol} - {target_mode.upper()} dimulai di background. Cek Logs untuk progress."}

@router.post("/api/strategies/confirm-save")
async def confirm_save_model(req: ConfirmSaveModelRequest):
    """
    Konfirmasi dialog penyimpanan checkpoint model:
    - 'save': Menimpa file .pkl lama dengan model baru, memperbarui metadata & scorecard, serta mengaktifkan model.
    - 'discard': Membuang model baru tanpa menyentuh file .pkl lama.
    """
    sym = (req.symbol or getattr(bot.researcher, "symbol", "XAUUSD")).upper()
    mode = req.mode.lower()
    action = req.action.lower()

    if getattr(bot.researcher, "symbol", "XAUUSD").upper() != sym:
        bot.researcher.set_symbol(sym)

    if action == "save":
        success, msg, info = bot.researcher.apply_pending_model(mode)
        if success:
            passed = info.get("passed_oos", False)
            if mode == "normal":
                bot.supervisor.set_model_validity(passed, bot.supervisor.is_runner_valid(sym), symbol=sym)
            else:
                bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(sym), passed, symbol=sym)
            return {
                "status": "success",
                "symbol": sym,
                "mode": mode,
                "action": "save",
                "message": msg,
                "info": info
            }
        else:
            return {"status": "error", "message": msg}
    elif action == "discard":
        success, msg = bot.researcher.discard_pending_model(mode)
        return {
            "status": "success" if success else "error",
            "symbol": sym,
            "mode": mode,
            "action": "discard",
            "message": msg
        }
    else:
        return {"status": "error", "message": f"Action '{action}' tidak dikenal. Gunakan 'save' atau 'discard'."}

@router.post("/api/strategies/reset-models")
async def reset_models(req: Optional[ResetModelRequest] = None):
    """
    Reset Otak AI:
    Menghapus SELURUH file .pkl (utama, kandidat, pending), SEMUA metadata dan metric JSON di models/{sym}/,
    menghapus semua riwayat metric scorecard di database untuk pair ini,
    mengosongkan tabel hard_negatives, dan mengembalikan in-memory state ke Fresh Quantitative Baseline.
    """
    from database import reset_ai_trade_history, delete_scorecards_by_symbol

    sym = (req.symbol if req and req.symbol else getattr(bot.researcher, "symbol", "XAUUSD")).upper()

    # 1. Hapus SELURUH file model (.pkl), candidate, pending, dan metadata/scorecard JSON di folder models/{sym}/
    deleted_files = ModelManager.reset_all_models_and_metrics(sym)

    # 2. Hapus seluruh riwayat metric scorecard di database untuk pair ini
    cleared_scorecards = delete_scorecards_by_symbol(sym)

    # 3. Truncate tabel hard_negatives
    cleared_hn = 0
    try:
        cleared_hn = reset_ai_trade_history(categories=["hard_negatives"])
        logging.info(f"🗑️ [API RESET] Tabel hard_negatives dibersihkan ({cleared_hn} baris dihapus).")
    except Exception as e_hn:
        logging.warning(f"Gagal membersihkan hard_negatives: {e_hn}")

    # 4. Reset in-memory state Researcher & Supervisor jika sedang mengelola pair ini
    if getattr(bot.researcher, "symbol", "XAUUSD").upper() == sym:
        bot.researcher.model_normal = None
        bot.researcher.model_runner = None
        bot.researcher.features = []
        bot.researcher.last_accuracy_normal = 0.0
        bot.researcher.last_accuracy_runner = 0.0
        bot.researcher.last_trained_normal = "Never"
        bot.researcher.last_trained_runner = "Never"
        bot.researcher.optimal_threshold_normal = 0.54
        bot.researcher.optimal_threshold_runner = 0.54
        bot.researcher.oos_scorecard = {"normal": None, "runner": None}
        bot.researcher.pending_training = {}
        bot.supervisor.set_model_validity(False, False, symbol=sym)
        bot.supervisor.isolate_quarantine("all", symbol=sym)

    # 5. Reset gatekeeper metrics
    if hasattr(bot, "gatekeeper"):
        bot.gatekeeper.last_metrics = {"normal": {}, "runner": {}}

    return {
        "status": "success",
        "symbol": sym,
        "message": f"Fresh Quantitative Baseline ({sym}) aktif: Seluruh file .pkl, metadata, dan metrik scorecard di database berhasil dihapus bersih.",
        "deleted_files": deleted_files,
        "cleared_scorecards": cleared_scorecards,
        "cleared_hard_negatives": cleared_hn,
    }

class EvaluateOosRequest(BaseModel):
    symbol: Optional[str] = "AUTO"
    mode: Optional[str] = "normal"  # "normal", "runner", or "all"
    sample_candles: Optional[int] = 50000
    custom_thresholds: Optional[dict] = None

@router.post("/api/strategies/evaluate-oos")
async def evaluate_oos(req: EvaluateOosRequest = EvaluateOosRequest()):
    """Trigger evaluasi manual Fit & Proper Test pada data OOS menggunakan VectorBT."""
    target_symbol = str(req.symbol or "AUTO").strip().upper()
    if target_symbol == "AUTO":
        target_symbol = bot.active_symbol or "XAUUSD"

    canonical_symbol = target_symbol.upper().rstrip("MC")
    bot.researcher.set_symbol(canonical_symbol)

    modes_to_evaluate = ["normal", "runner"] if req.mode.lower() == "all" else [req.mode.lower()]
    models_dict = {}
    for m in modes_to_evaluate:
        current_model = bot.researcher.model_normal if m == "normal" else bot.researcher.model_runner
        if current_model is None:
            bot.researcher.load_models()
            current_model = bot.researcher.model_normal if m == "normal" else bot.researcher.model_runner
        if current_model is None:
            return {
                "status": "error",
                "message": f"Model {m.upper()} untuk {canonical_symbol} belum pernah dilatih atau tidak ditemukan di disk."
            }
        models_dict[m] = current_model

    import pandas as pd
    from agents.research.oos_evaluator import run_fit_proper_test
    from agents.research.model_manager import ModelManager

    total_chunks, test_gen = bot.data_miner.load_test_chunks(
        chunk_size=req.sample_candles,
        symbol=target_symbol,
        max_test_samples=req.sample_candles
    )

    if total_chunks == 0 or test_gen is None:
        return {
            "status": "error",
            "message": f"Tidak ada data OOS/Test di database untuk {target_symbol}. Jalankan backfill data terlebih dahulu."
        }

    try:
        df_oos = pd.concat(list(test_gen))
    except Exception as e:
        return {"status": "error", "message": f"Gagal membaca data OOS: {e}"}

    if df_oos.empty or len(df_oos) < 30:
        return {
            "status": "error",
            "message": f"Data OOS terlalu sedikit ({len(df_oos)} baris). Minimal 30 candle dibutuhkan untuk evaluasi."
        }

    results = {}
    from database import save_scorecard_record, get_scorecard_history, get_latest_scorecards
    start_dt = df_oos.index[0] if (hasattr(df_oos.index, 'strftime') and len(df_oos) > 0) else None
    end_dt = df_oos.index[-1] if (hasattr(df_oos.index, 'strftime') and len(df_oos) > 0) else None

    for m, m_obj in models_dict.items():
        scorecard = run_fit_proper_test(
            model=m_obj,
            researcher=bot.researcher,
            df_oos=df_oos,
            mode=m,
            symbol=canonical_symbol,
            custom_thresholds=req.custom_thresholds
        )
        results[m] = scorecard
        ModelManager.save_oos_scorecard(canonical_symbol, m, scorecard)
        try:
            save_scorecard_record(scorecard, oos_start_date=start_dt, oos_end_date=end_dt)
        except Exception as e_rec:
            logging.warning(f"Gagal menyimpan scorecard ke database: {e_rec}")

    return {
        "status": "success",
        "symbol": canonical_symbol,
        "sample_candles": len(df_oos),
        "results": results if req.mode.lower() == "all" else results[req.mode.lower()]
    }

@router.get("/api/strategies/scorecard")
async def get_scorecards(
    symbol: Optional[str] = "XAUUSD",
    mode: Optional[str] = None,
    page: int = 1,
    limit: int = 20
):
    """Mengambil riwayat kronologis scorecard model (paginated)."""
    target_symbol = str(symbol or "XAUUSD").strip().upper()
    if target_symbol == "AUTO":
        target_symbol = bot.active_symbol or "XAUUSD"
    canonical_symbol = target_symbol.upper().rstrip("MC")

    from database import get_scorecard_history
    return get_scorecard_history(symbol=canonical_symbol, mode=mode, page=page, limit=limit)

@router.get("/api/strategies/scorecard/latest")
async def get_latest_scorecard(symbol: Optional[str] = "XAUUSD"):
    """Mengambil scorecard terkini untuk kedua mode ('normal' dan 'runner')."""
    target_symbol = str(symbol or "XAUUSD").strip().upper()
    if target_symbol == "AUTO":
        target_symbol = bot.active_symbol or "XAUUSD"
    canonical_symbol = target_symbol.upper().rstrip("MC")

    from database import get_latest_scorecards
    return get_latest_scorecards(symbol=canonical_symbol)
@router.get("/api/strategies/features")
async def get_feature_importance(
    symbol: Optional[str] = "XAUUSD",
    mode: Optional[str] = "normal",
    top_n: int = 10,
    importance_type: str = "gain"
):
    """
    TD#1: Mengembalikan Top-N Feature Importance (Gain / Split) dari model yang sedang aktif.
    Digunakan oleh halaman Strategi (Dapur AI) untuk visualisasi bar chart transparansi AI.
    """
    sym = (symbol or "XAUUSD").upper()
    mode_clean = (mode or "normal").lower()
    imp_type = (importance_type or "gain").lower()

    # Muat model dari in-memory researcher atau dari disk
    is_same_pair = (getattr(bot.researcher, "symbol", "XAUUSD").upper() == sym)
    if is_same_pair:
        model = bot.researcher.model_normal if mode_clean == "normal" else bot.researcher.model_runner
        features = list(getattr(bot.researcher, "features", []) or [])
    else:
        loaded = ModelManager.load_models(sym)
        model = loaded.get("model_normal") if mode_clean == "normal" else loaded.get("model_runner")
        features = loaded.get("features", [])

    if model is None:
        return {
            "status": "error",
            "message": f"Model {mode_clean.upper()} untuk {sym} belum dilatih. Jalankan Full Training terlebih dahulu.",
            "features": []
        }

    importance_list = extract_feature_importance(
        model=model,
        features=features or None,
        top_n=top_n,
        importance_type=imp_type
    )

    return {
        "status": "success",
        "symbol": sym,
        "mode": mode_clean,
        "importance_type": imp_type,
        "top_n": len(importance_list),
        "features": importance_list
    }

# =========================================================================
# AI INCUBATOR: BATCH TRAINING QUEUE PIPELINE
# =========================================================================

import uuid

class TrainingQueueManager:
    """
    Manajer Antrean Pelatihan Batch (Training Queue Pipeline).
    Mengeksekusi serangkaian tugas pelatihan AI (Full/Incremental) secara sekuensial (FIFO),
    dengan pelacakan progres per-tugas, opsi auto-apply checkpoint model yang lulus OOS,
    dan eksekusi aksi otomatis pasca antrean (Kembali IDLE atau FORCE LIVE).
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.tasks: list[dict] = []
        self.is_running: bool = False
        self.current_task_id: Optional[str] = None
        self.post_completion_action: str = "idle" # "idle" or "force_live"
        self.auto_apply: bool = True
        self.cancel_requested: bool = False
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None

    def get_status(self) -> dict:
        with self._lock:
            total = len(self.tasks)
            completed_count = sum(1 for t in self.tasks if t.get("status") in ["completed", "failed", "cancelled"])
            return {
                "status": "success",
                "is_running": self.is_running,
                "current_task_id": self.current_task_id,
                "post_completion_action": self.post_completion_action,
                "auto_apply": self.auto_apply,
                "total_tasks": total,
                "completed_tasks": completed_count,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "tasks": [dict(t) for t in self.tasks]
            }

    def cancel_queue(self) -> dict:
        with self._lock:
            if not self.is_running:
                for t in self.tasks:
                    if t.get("status") == "pending":
                        t["status"] = "cancelled"
                return {"status": "success", "message": "Antrean telah dibersihkan."}
            self.cancel_requested = True
            for t in self.tasks:
                if t.get("status") == "pending":
                    t["status"] = "cancelled"
            return {"status": "success", "message": "Permintaan pembatalan antrean berhasil diajukan."}

    def start_queue(self, task_items: list[QueueTaskItem], post_completion_action: str = "idle", auto_apply: bool = True) -> tuple[bool, str]:
        with self._lock:
            if self.is_running:
                return False, "Antrean training saat ini masih berjalan. Batalkan atau tunggu hingga selesai."
            if not task_items:
                return False, "Daftar tugas antrean kosong. Tambahkan minimal 1 tugas latihan."

            self.tasks = []
            for item in task_items:
                self.tasks.append({
                    "id": item.id or str(uuid.uuid4())[:8],
                    "symbol": item.symbol.upper(),
                    "mode": item.mode.lower(),
                    "type": item.type.lower(),
                    "status": "pending",
                    "progress": "Menunggu antrean...",
                    "started_at": None,
                    "completed_at": None,
                    "accuracy": 0.0,
                    "passed_oos": False,
                    "error": None
                })
            self.is_running = True
            self.cancel_requested = False
            self.post_completion_action = post_completion_action.lower()
            self.auto_apply = auto_apply
            self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.completed_at = None

        thread = threading.Thread(target=self._worker, daemon=True)
        thread.start()
        return True, f"Antrean training dengan {len(self.tasks)} tugas berhasil diluncurkan."

    def _worker(self):
        try:
            for task in self.tasks:
                with self._lock:
                    if self.cancel_requested:
                        if task["status"] == "pending":
                            task["status"] = "cancelled"
                        continue
                    self.current_task_id = task["id"]
                    task["status"] = "running"
                    task["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    task["progress"] = f"Melatih {task['symbol']} {task['mode'].upper()} ({task['type'].upper()})..."

                sym = task["symbol"]
                mode = task["mode"]
                train_type = task["type"]

                logging.info(f"🚀 [QUEUE WORKER] Memulai Task {task['id']}: {sym} - {mode.upper()} ({train_type.upper()})...")

                try:
                    bot.data_miner.set_symbol(sym)
                    bot.researcher.set_symbol(sym)

                    total_chunks, data_generator = bot.data_miner.load_train_chunks(
                        chunk_size=100000, mode=mode, symbol=sym
                    )

                    if total_chunks == 0 or data_generator is None:
                        raise ValueError(f"Database {bot.data_miner.table_name} kosong atau tidak ada candle data.")

                    bot.researcher._current_train_type = train_type
                    if train_type == "full":
                        bot.researcher.features = []

                    if mode == "normal":
                        bot.researcher.is_training_normal = True
                        try:
                            bot.researcher.train_normal_mode(
                                data_generator,
                                total_chunks=total_chunks,
                                data_miner=bot.data_miner,
                                train_type=train_type
                            )
                        finally:
                            bot.researcher.is_training_normal = False
                    else:
                        bot.researcher.is_training_runner = True
                        try:
                            bot.researcher.train_runner_mode(
                                data_generator,
                                total_chunks=total_chunks,
                                data_miner=bot.data_miner,
                                train_type=train_type
                            )
                        finally:
                            bot.researcher.is_training_runner = False

                    p_info = bot.researcher.pending_training.get(mode, {}).get("info", {})
                    acc = float(p_info.get("candidate_accuracy", 0.0))
                    passed = bool(p_info.get("passed_oos", False))

                    with self._lock:
                        task["accuracy"] = acc
                        task["passed_oos"] = passed

                    if self.auto_apply:
                        apply_success, apply_msg, _ = bot.researcher.apply_pending_model(mode)
                        if apply_success:
                            if mode == "normal":
                                bot.supervisor.set_model_validity(passed, bot.supervisor.is_runner_valid(sym), symbol=sym)
                            else:
                                bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(sym), passed, symbol=sym)
                            logging.info(f"✅ [QUEUE WORKER] Model {mode} ({sym}) auto-applied: {apply_msg}")

                    with self._lock:
                        task["status"] = "completed"
                        task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        task["progress"] = f"Selesai! Win Rate OOS: {acc*100:.1f}% ({'LULUS' if passed else 'TIDAK LULUS'})"

                    logging.info(f"✅ [QUEUE WORKER] Task {task['id']} selesai: {sym} {mode} - Acc: {acc*100:.1f}%.")

                except Exception as ex:
                    import traceback
                    logging.error(f"❌ [QUEUE WORKER] Task {task['id']} gagal: {ex}")
                    logging.error(traceback.format_exc())
                    with self._lock:
                        task["status"] = "failed"
                        task["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        task["error"] = str(ex)
                        task["progress"] = f"Gagal: {str(ex)[:120]}"

            with self._lock:
                self.is_running = False
                self.current_task_id = None
                self.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                final_action = self.post_completion_action
                was_cancelled = self.cancel_requested

            # Eksekusi aksi pasca antrean (Post Completion Action)
            if not was_cancelled:
                if final_action == "force_live":
                    logging.info("🚀 [TRAINING QUEUE] Seluruh tugas selesai. Mengeksekusi FORCE LIVE MODE...")
                    bot.supervisor.force_live_mode("all")
                    bot.is_live = True
                    bot.active_since = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    bot.supervisor.state = "live"
                    if not bot.mt5_connected:
                        try:
                            bot.connect_mt5()
                        except Exception as e_mt5:
                            logging.warning(f"Gagal menghubungkan MT5: {e_mt5}")
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running() and (bot.executor_task is None or bot.executor_task.done()):
                            bot.executor_task = loop.create_task(bot.executor.monitor_market())
                    except Exception as e_loop:
                        logging.warning(f"Executor loop dispatch info: {e_loop}")
                else:
                    logging.info("⏸️ [TRAINING QUEUE] Seluruh tugas selesai. Sistem standby dalam mode IDLE.")
                    bot.is_live = False
                    bot.active_since = None
                    bot.supervisor.state = "idle"
                    bot.executor.running = False
                    if bot.executor_task:
                        try:
                            bot.executor_task.cancel()
                        except Exception:
                            pass
        except Exception as e_fatal:
            logging.error(f"[QUEUE WORKER FATAL ERROR] {e_fatal}")
            with self._lock:
                self.is_running = False
                self.current_task_id = None

training_queue_manager = TrainingQueueManager()

@router.post("/api/strategies/queue-train")
async def trigger_queue_train(req: QueueTrainRequest):
    """
    Menjalankan antrean pelatihan AI (Batch Training Queue).
    Menerima daftar tugas (mode, type, symbol) dan opsi pasca antrean ('idle' atau 'force_live').
    """
    success, msg = training_queue_manager.start_queue(
        task_items=req.tasks,
        post_completion_action=req.post_completion_action,
        auto_apply=req.auto_apply
    )
    if not success:
        return {"status": "error", "message": msg}
    return {
        "status": "success",
        "message": msg,
        "queue_status": training_queue_manager.get_status()
    }

@router.get("/api/strategies/queue-status")
async def get_queue_status():
    """Mengembalikan status langsung dari Training Queue Pipeline."""
    return training_queue_manager.get_status()

@router.post("/api/strategies/queue-cancel")
async def cancel_queue_training():
    """Membatalkan seluruh antrean tugas latihan yang tersisa."""
    return training_queue_manager.cancel_queue()



