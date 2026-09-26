"use client";

import { useState, useEffect } from "react";
import { Settings2, RotateCcw, Loader2, Brain, Layers, FolderCheck } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import { RiskManagementCard } from "@/components/strategies/RiskManagementCard";
import { AiEntryThresholdCard } from "@/components/strategies/AiEntryThresholdCard";
import { ModelStatusGrid } from "@/components/strategies/ModelStatusGrid";
import { RlhfReviewQueue } from "@/components/strategies/RlhfReviewQueue";
import { ConfirmModal } from "@/components/ui/ConfirmModal";

export default function StrategiesPage() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [isResetModalOpen, setIsResetModalOpen] = useState(false);
  const [portfolioEquity, setPortfolioEquity] = useState(1000);
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
      console.error("Failed to fetch pairs in strategies", err);
    }
  };

  const fetchStrategyStatus = async (sym = selectedPair) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/status?symbol=${sym}`);
      const data = await res.json();
      if (data.status === "success" && data.models_status) {
        setModelsStatus(data.models_status);
      }
    } catch (err) {
      console.error("Failed to fetch strategy status", err);
    }
  };

  useEffect(() => {
    fetchPairs();
    // Ambil equity portfolio
    fetch(`${getApiBaseUrl()}/api/state`)
      .then((res) => res.json())
      .then((data) => {
        if (data.portfolio?.equity) setPortfolioEquity(data.portfolio.equity);
      })
      .catch((err) => console.error(err));
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
        body: JSON.stringify({ mode }),
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

  const handleTrainMode = async (mode: string, type: "incremental" | "full") => {
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
        data.message || `Seluruh model lama di models/${selectedPair}/ berhasil di-reset.`,
        `Reset Otak ${selectedPair}`
      );
      setModelsStatus({
        normal: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0, last_trained: null },
        runner: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0, last_trained: null },
      });
      setIsResetModalOpen(false);
      fetchPairs();
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
            <Settings2 className="text-brand-green w-7 h-7" />
            Strategies &amp; AI Incubator
          </h1>
          <p className="text-xs sm:text-sm text-white/50 mt-1">
            Manajemen risiko transaksi, pelatihan mandiri LightGBM (Isolated Brain per Pair), dan validasi kurasi RLHF.
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

        <div className="flex items-center gap-2 text-xs text-white/40">
          <FolderCheck size={14} className="text-brand-green" />
          <span>Folder Otak: <strong className="text-white/80 font-mono">models/{selectedPair}/</strong></span>
        </div>
      </div>

      {/* 1. Risk Management Card Component */}
      <RiskManagementCard portfolioEquity={portfolioEquity} />

      {/* 2. AI Signal Entry Threshold Card Component */}
      <AiEntryThresholdCard />

      {/* 3. Model Status & Control Grid Component */}
      <div className="mb-2">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
            <Brain size={16} className="text-brand-green" /> Status &amp; Kontrol Pelatihan Otak ({selectedPair})
          </h2>
        </div>
        <ModelStatusGrid
          modelsStatus={modelsStatus}
          loading={loading}
          onTrain={handleTrainMode}
          onForceMode={handleForceMode}
          onToggleBrain={handleToggleBrain}
        />
      </div>

      {/* 4. RLHF Review Queue Component */}
      <RlhfReviewQueue />

      {/* Custom Confirmation Modal */}
      <ConfirmModal
        isOpen={isResetModalOpen}
        onClose={() => !loading && setIsResetModalOpen(false)}
        onConfirm={handleConfirmResetModels}
        title={`Konfirmasi Reset Otak ${selectedPair}`}
        description={`Tindakan ini hanya akan menghapus file model LightGBM (.pkl) di dalam subfolder models/${selectedPair}/ dan membersihkan hard_negatives. Otak pair lainnya (seperti XAUUSD atau pair lain) TIDAK AKAN terhapus. Lanjutkan?`}
        confirmText={`Reset Otak ${selectedPair}`}
        cancelText="Batal"
        variant="warning"
        isLoading={loading}
      />
    </div>
  );
}
