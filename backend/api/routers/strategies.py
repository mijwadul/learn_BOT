import logging
import threading
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

from ..dependencies import bot

router = APIRouter(tags=["Strategies & Training"])

class ModeRequest(BaseModel):
    mode: str

class TrainRequest(BaseModel):
    type: str # 'full' or 'incremental'
    mode: str # 'normal' or 'runner'

class MicroTrainRequest(BaseModel):
    mode: str = "all" # "normal", "runner", or "all"

@router.post("/api/strategies/force_live")
async def force_live(req: ModeRequest):
    bot.supervisor.force_live_mode(req.mode)
    if bot.supervisor.state == 'live':
        bot.is_live = True
    return {"status": "success", "mode": req.mode, "action": "force_live", "state": bot.supervisor.state}

@router.post("/api/strategies/quarantine")
async def quarantine(req: ModeRequest):
    bot.supervisor.isolate_quarantine(req.mode)
    return {"status": "success", "mode": req.mode, "action": "quarantine", "state": bot.supervisor.state}

@router.post("/api/strategies/train")
async def train_model(req: TrainRequest):
    def _train_task():
        try:
            logging.info(f"Memulai pelatihan AI ({req.type}) untuk {req.mode} Mode...")

            total_chunks, data_generator = bot.data_miner.load_train_chunks(chunk_size=5000, mode=req.mode)
            if total_chunks == 0 or data_generator is None:
                logging.warning("⚠️ Training dibatalkan: Database market_data kosong. Jalankan Force Backfill MT5 terlebih dahulu.")
                return
                
            total_test_chunks, test_generator = bot.data_miner.load_test_chunks(chunk_size=5000)

            if req.type == 'full':
                if req.mode == 'normal':
                    bot.researcher.model_normal = None
                    logging.info("[FULL TRAIN] Model Normal di-reset. Melatih dari awal...")
                elif req.mode == 'runner':
                    bot.researcher.model_runner = None
                    logging.info("[FULL TRAIN] Model Runner di-reset. Melatih dari awal...")

            if req.mode == 'normal':
                bot.researcher.is_training_normal = True
                try:
                    result = bot.researcher.train_normal_mode(data_generator, total_chunks=total_chunks)
                    if result:
                        if test_generator and total_test_chunks > 0:
                            accuracy = bot.gatekeeper.validate_model('normal', test_generator, total_test_chunks)
                            bot.researcher.last_accuracy_normal = float(accuracy)
                            bot.researcher.last_trained_normal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            bot.researcher.save_metadata()
                            if accuracy > 0.50:
                                bot.supervisor.set_model_validity(True, bot.supervisor.is_runner_valid())
                                logging.info("✅ Model Normal lulus validasi. Supervisor Normal Mode = VALID.")
                            else:
                                bot.supervisor.set_model_validity(False, bot.supervisor.is_runner_valid())
                                logging.warning("❌ Model Normal gagal validasi (<50%). Supervisor Normal Mode = QUARANTINE.")
                        else:
                            bot.supervisor.set_model_validity(True, bot.supervisor.is_runner_valid())
                            bot.researcher.last_trained_normal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            bot.researcher.save_metadata()
                            logging.info("✅ Model Normal dilatih tanpa OOS. Supervisor Normal Mode = VALID.")
                finally:
                    bot.researcher.is_training_normal = False
            elif req.mode == 'runner':
                bot.researcher.is_training_runner = True
                try:
                    result = bot.researcher.train_runner_mode(data_generator, total_chunks=total_chunks)
                    if result:
                        if test_generator and total_test_chunks > 0:
                            accuracy = bot.gatekeeper.validate_model('runner', test_generator, total_test_chunks)
                            bot.researcher.last_accuracy_runner = float(accuracy)
                            bot.researcher.last_trained_runner = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            bot.researcher.save_metadata()
                            if accuracy > 0.50:
                                bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(), True)
                                logging.info("✅ Model Runner lulus validasi. Supervisor Runner Mode = VALID.")
                            else:
                                bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(), False)
                                logging.warning("❌ Model Runner gagal validasi (<50%). Supervisor Runner Mode = QUARANTINE.")
                        else:
                            bot.supervisor.set_model_validity(bot.supervisor.is_normal_valid(), True)
                            bot.researcher.last_trained_runner = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            bot.researcher.save_metadata()
                            logging.info("✅ Model Runner dilatih tanpa OOS. Supervisor Runner Mode = VALID.")
                finally:
                    bot.researcher.is_training_runner = False

            logging.info(f"✅ Pelatihan AI ({req.type}) untuk {req.mode} Mode selesai.")
        except Exception as e:
            import traceback
            logging.error(f"Training failed: {e}")
            logging.error(traceback.format_exc())

    threading.Thread(target=_train_task, daemon=True).start()
    return {"status": "success", "message": f"{req.type.capitalize()} Training {req.mode} mode started in background. Cek Logs untuk progress."}

@router.post("/api/strategies/micro-train")
async def trigger_micro_train(req: MicroTrainRequest = None):
    """Memicu Online Learning Micro-Retrain secara on-demand / manual."""
    target_mode = req.mode.lower() if req and req.mode else "all"

    def _micro_task():
        try:
            logging.info(f"[API MICRO-TRAIN] Memulai Micro-Retrain on-demand untuk mode: {target_mode.upper()}...")
            if bot.data_miner and bot.mt5_connected:
                try:
                    logging.info("[API MICRO-TRAIN] Sinkronisasi candle MT5 terbaru ke database sebelum retrain...")
                    bot.data_miner.sync_latest_data()
                except Exception as e_sync:
                    logging.warning(f"[API MICRO-TRAIN] Gagal auto-sync MT5: {e_sync}")

            df_recent = bot.data_miner.load_recent_micro_chunk(n_candles=3000)
            if df_recent is None or df_recent.empty:
                logging.warning("[API MICRO-TRAIN] Data candle recent kosong di database.")
                return

            if target_mode in ["normal", "all"] and bot.researcher.model_normal is not None:
                fb_normal = bot.data_miner.load_live_decision_chunk(mode="normal")
                bot.researcher.micro_retrain("normal", df_recent, fb_normal)

            if target_mode in ["runner", "all"] and bot.researcher.model_runner is not None:
                fb_runner = bot.data_miner.load_live_decision_chunk(mode="runner")
                bot.researcher.micro_retrain("runner", df_recent, fb_runner)

            bot.executor.last_micro_retrain_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"✅ [API MICRO-TRAIN] Micro-Retrain selesai pada {bot.executor.last_micro_retrain_time}.")
        except Exception as e:
            logging.error(f"[API MICRO-TRAIN] Gagal: {e}")

    threading.Thread(target=_micro_task, daemon=True).start()
    return {"status": "success", "message": f"Online Micro-Retrain ({target_mode.upper()}) started in background. Cek Logs untuk progress."}
