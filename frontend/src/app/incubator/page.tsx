"use client";

import { useState, useEffect } from "react";
import { Brain, RotateCcw, Loader2, Sparkles, Layers } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import { TrainingQueueCard } from "@/components/strategies/TrainingQueueCard";
import { ModelStatusGrid } from "@/components/strategies/ModelStatusGrid";
import { ModelScorecardSection } from "@/components/strategies/ModelScorecardSection";
import { RlhfReviewQueue } from "@/components/strategies/RlhfReviewQueue";
import { FeatureImportanceCard } from "@/components/strategies/FeatureImportanceCard";
import { ConfirmModal } from "@/components/ui/ConfirmModal";
import { ConfirmSaveModelModal, PendingModelInfo } from "@/components/strategies/ConfirmSaveModelModal";

export default function AiIncubatorPage() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [isResetModalOpen, setIsResetModalOpen] = useState(false);
  const [fullTrainModal, setFullTrainModal] = useState<{
    isOpen: boolean;
    mode: "normal" | "runner" | null;
  }>({ isOpen: false, mode: null });
  const [pendingModels, setPendingModels] = useState<{ normal?: PendingModelInfo | null; runner?: PendingModelInfo | null }>({});
  const [saveModal, setSaveModal] = useState<{
    isOpen: boolean;
    mode: "normal" | "runner" | null;
    data: PendingModelInfo | null;
  }>({ isOpen: false, mode: null, data: null });
  const [dismissedPending, setDismissedPending] = useState<Record<string, string>>({});
  const [pairs, setPairs] = useState<any[]>([{ symbol: "XAUUSD" }]);
  const [selectedPair, setSelectedPair] = useState<string>("XAUUSD");
  const [modelsStatus, setModelsStatus] = useState({
    normal: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0, last_trained: null },
    runner: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0, last_trained: null },
  });

  // Fetch list of registered pairs
  const fetchPairs = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/pairs`);
      const data = await res.json();
      if (data.status === "success" && data.pairs) {
        setPairs(data.pairs);
      }
    } catch (err) {
      console.error("Failed to fetch pairs in incubator", err);
    }
  };

  const fetchStrategyStatus = async (sym = selectedPair) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/status?symbol=${sym}`);
      const data = await res.json();
      if (data.status === "success") {
        if (data.models_status) {
          setModelsStatus(data.models_status);
        }
        if (data.pending_models) {
          setPendingModels(data.pending_models);
          // Otomatis buka dialog konfirmasi jika ada model baru hasil training yang belum pernah di-dismiss
          const modes: Array<"normal" | "runner"> = ["normal", "runner"];
          for (const m of modes) {
            const pData = data.pending_models[m];
            if (pData && pData.trained_at) {
              const key = `${sym}_${m}_${pData.trained_at}`;
              if (!dismissedPending[key] && !saveModal.isOpen) {
                setSaveModal({ isOpen: true, mode: m, data: pData });
                break;
              }
            }
          }
        } else {
          setPendingModels({});
        }
      }
    } catch (err) {
      console.error("Failed to fetch strategy status in incubator", err);
    }
  };

  useEffect(() => {
    fetchPairs();
  }, []);

  useEffect(() => {
    fetchStrategyStatus(selectedPair);
    const interval = setInterval(() => fetchStrategyStatus(selectedPair), 3000);
    return () => clearInterval(interval);
  }, [selectedPair]);

  const handleToggleBrain = async (mode: "normal" | "runner" | "all", active: boolean) => {
    setLoading(true);
    try {
      const endpoint = mode === "all" ? "/api/strategies/toggle-all-brains" : "/api/strategies/toggle-brain";
      const body = mode === "all" ? { active, symbol: selectedPair } : { mode, active, symbol: selectedPair };
      const res = await fetch(`${getApiBaseUrl()}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.success(data.message, "Saklar Otak AI");
        fetchStrategyStatus(selectedPair);
      } else {
        toast.warning(data.message || "Gagal mengubah status otak.", "Perhatian");
      }
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Error");
    } finally {
      setLoading(false);
    }
  };

  const handleForceMode = async (mode: string, action: "force_live" | "quarantine") => {
    setLoading(true);
    try {
      const endpoint = action === "force_live" ? "/api/strategies/force_live" : "/api/strategies/quarantine";
      const res = await fetch(`${getApiBaseUrl()}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, symbol: selectedPair }),
      });
      const data = await res.json();
      toast.info(`[${action.toUpperCase()}] diterapkan ke ${mode.toUpperCase()}. State: ${data.state}`, "Status Mode");
      fetchStrategyStatus(selectedPair);
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Error");
    } finally {
      setLoading(false);
    }
  };

  const executeTrain = async (mode: string, type: "incremental" | "full") => {
    setLoading(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/train`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, type, symbol: selectedPair }),
      });
      const data = await res.json();
      toast.success(data.message || `Pelatihan ${mode} untuk ${selectedPair} dimulai.`, `${type.toUpperCase()} Training (${selectedPair})`);
    } catch {
      toast.error("Gagal memicu pelatihan model.", "Error");
    } finally {
      setLoading(false);
      setFullTrainModal({ isOpen: false, mode: null });
    }
  };

  const handleTrainMode = (mode: string, type: "incremental" | "full") => {
    if (type === "full") {
      setFullTrainModal({ isOpen: true, mode: mode as "normal" | "runner" });
    } else {
      executeTrain(mode, "incremental");
    }
  };

  const handleReviewPending = (mode: "normal" | "runner") => {
    const pData = pendingModels[mode];
    if (pData) {
      setSaveModal({ isOpen: true, mode, data: pData });
    }
  };

  const handleSavePendingModel = async (action: "save" | "discard") => {
    if (!saveModal.mode) return;
    setLoading(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/confirm-save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: selectedPair,
          mode: saveModal.mode,
          action
        })
      });
      const data = await res.json();
      if (data.status === "success") {
        if (action === "save") {
          toast.success(
            data.message || `Model ${saveModal.mode.toUpperCase()} (${selectedPair}) berhasil disimpan menimpa .pkl lama!`,
            "Checkpoint Model Disimpan"
          );
        } else {
          toast.info(
            data.message || `Model ${saveModal.mode.toUpperCase()} baru dibuang. Model .pkl lama tetap aktif.`,
            "Model Ditolak"
          );
        }
        if (saveModal.data?.trained_at) {
          const key = `${selectedPair}_${saveModal.mode}_${saveModal.data.trained_at}`;
          setDismissedPending(prev => ({ ...prev, [key]: "processed" }));
        }
        setSaveModal({ isOpen: false, mode: null, data: null });
        fetchStrategyStatus(selectedPair);
        fetchPairs();
      } else {
        toast.error(data.message || "Gagal memproses konfirmasi model.", "Error");
      }
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Error");
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmResetModels = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/reset-models`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: selectedPair })
      });
      const data = await res.json();
      toast.success(
        data.message || `Seluruh model .pkl dan semua metric yang tersimpan untuk ${selectedPair} berhasil terhapus bersih.`,
        `Reset Otak ${selectedPair}`
      );
      setModelsStatus({
        normal: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0, last_trained: null },
        runner: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0, last_trained: null },
      });
      setPendingModels({});
      setSaveModal({ isOpen: false, mode: null, data: null });
      setIsResetModalOpen(false);
      fetchPairs();
      fetchStrategyStatus(selectedPair);
    } catch {
      toast.error(`Gagal mereset model ${selectedPair}.`, "Error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 md:p-8 flex flex-col min-h-full">
      {/* Page Header */}
      <div className="mb-4 shrink-0 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight flex items-center gap-3">
            <Brain className="text-brand-green w-7 h-7" />
            AI Incubator &amp; Training Lab
          </h1>
          <p className="text-xs sm:text-sm text-white/50 mt-1">
            Laboratorium pelatihan mandiri LightGBM (Batch Queue Training), OOS Fit &amp; Proper Test, transparansi feature importance, dan kurasi RLHF.
          </p>
        </div>
        <button
          onClick={() => setIsResetModalOpen(true)}
          disabled={loading}
          className="self-start sm:self-auto px-4 py-2.5 rounded-xl text-xs font-bold text-amber-400 hover:text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 transition-all flex items-center gap-2 disabled:opacity-50 cursor-pointer"
          title={`Hapus file .pkl di models/${selectedPair}/ dan reset otak ${selectedPair}`}
        >
          {loading ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <RotateCcw className="w-3.5 h-3.5" />
          )}
          {loading ? "Mereset..." : `Reset Otak (${selectedPair})`}
        </button>
      </div>

      {/* Brain Pair Selector Bar */}
      <div className="mb-6 p-3.5 rounded-2xl bg-black/40 border border-white/10 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 overflow-x-auto py-1">
          <span className="text-xs font-semibold text-white/50 uppercase tracking-wider mr-1 flex items-center gap-1.5">
            <Brain size={16} className="text-brand-green" /> Pilih Otak Pair:
          </span>
          {(pairs.length > 0 ? pairs.map(p => p.symbol) : ["XAUUSD"]).map((sym) => {
            const isSelected = selectedPair === sym;
            const pairData = pairs.find(p => p.symbol === sym);
            const isTrained = pairData?.has_normal_model || pairData?.has_runner_model;
            return (
              <button
                key={sym}
                onClick={() => setSelectedPair(sym)}
                className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                  isSelected
                    ? "bg-brand-green text-black shadow-lg shadow-brand-green/30 border border-brand-green"
                    : "bg-white/5 hover:bg-white/10 text-white/70 border border-white/5"
                }`}
              >
                <span>{sym}</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded font-semibold ${
                  isSelected 
                    ? "bg-black/20 text-black font-bold" 
                    : isTrained 
                    ? "bg-brand-green/20 text-brand-green border border-brand-green/40" 
                    : "bg-white/10 text-white/40"
                }`}>
                  {isTrained ? "Trained" : "Untrained"}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 1. BATCH TRAINING PIPELINE (QUEUE) */}
      <TrainingQueueCard 
        selectedPair={selectedPair} 
        pairs={pairs}
        onQueueComplete={() => {
          fetchStrategyStatus(selectedPair);
          fetchPairs();
        }}
      />

      {/* 2. Model Status & Individual Control Grid */}
      <div className="mb-2">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <Brain size={16} className="text-brand-green" /> Status &amp; Kontrol Pelatihan Manual ({selectedPair})
          </h2>
        </div>
        <ModelStatusGrid
          modelsStatus={modelsStatus}
          pendingModels={pendingModels}
          loading={loading}
          onTrain={handleTrainMode}
          onForceMode={handleForceMode}
          onToggleBrain={handleToggleBrain}
          onReviewPending={handleReviewPending}
        />
      </div>

      {/* 3. Feature Importance Card — Transparansi AI (Dapur AI) */}
      <FeatureImportanceCard selectedPair={selectedPair} />

      {/* 4. Model Health Report (Scorecard & OOS Fit & Proper Test) */}
      <ModelScorecardSection selectedPair={selectedPair} />

      {/* 5. RLHF Review Queue Component */}
      <RlhfReviewQueue selectedPair={selectedPair} />

      {/* Custom Confirmation Modal: Reset Otak */}
      <ConfirmModal
        isOpen={isResetModalOpen}
        onClose={() => !loading && setIsResetModalOpen(false)}
        onConfirm={handleConfirmResetModels}
        title={`Konfirmasi Reset Otak ${selectedPair}`}
        description={`PERINGATAN KERAS: Tindakan ini akan MENGHAPUS BERSIH seluruh file model (.pkl), candidate, pending, semua file metadata JSON di models/${selectedPair}/, serta SEMUA rekaman riwayat metrik scorecard di database. Seluruh riwayat performa model untuk pair ${selectedPair} akan dikembalikan ke Fresh Quantitative Baseline murni. Lanjutkan?`}
        confirmText={`Hapus & Reset Otak ${selectedPair}`}
        cancelText="Batal"
        variant="danger"
        isLoading={loading}
      />

      {/* Confirmation Modal: Force Full Training */}
      <ConfirmModal
        isOpen={fullTrainModal.isOpen}
        onClose={() => !loading && setFullTrainModal({ isOpen: false, mode: null })}
        onConfirm={() => { if (fullTrainModal.mode) executeTrain(fullTrainModal.mode, "full"); }}
        title={`Konfirmasi Force Full Training (${fullTrainModal.mode?.toUpperCase()} - ${selectedPair})`}
        description={`PERINGATAN: Force Full Training akan menjalankan optimasi hyperparameter Optuna (Purged Walk-Forward CV) dan melatih ulang model LightGBM secara utuh pada seluruh dataset historis (${selectedPair}). Proses ini menggunakan resource CPU secara intensif dan memakan waktu beberapa menit. Lanjutkan?`}
        confirmText={`Mulai Full Retrain (${fullTrainModal.mode?.toUpperCase()})`}
        cancelText="Batal"
        variant="warning"
        isLoading={loading}
      />

      {/* Modal Dialog Konfirmasi Penyimpanan Model Baru */}
      <ConfirmSaveModelModal
        isOpen={saveModal.isOpen}
        data={saveModal.data}
        isLoading={loading}
        onSave={() => handleSavePendingModel("save")}
        onDiscard={() => handleSavePendingModel("discard")}
        onClose={() => {
          if (saveModal.data?.trained_at && saveModal.mode) {
            const key = `${selectedPair}_${saveModal.mode}_${saveModal.data.trained_at}`;
            setDismissedPending(prev => ({ ...prev, [key]: "dismissed" }));
          }
          setSaveModal({ isOpen: false, mode: null, data: null });
        }}
      />
    </div>
  );
}
