"use client";

import { useState, useEffect } from "react";
import { Settings2, RotateCcw } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import { RiskManagementCard } from "@/components/strategies/RiskManagementCard";
import { ModelStatusGrid } from "@/components/strategies/ModelStatusGrid";
import { RlhfReviewQueue } from "@/components/strategies/RlhfReviewQueue";

export default function StrategiesPage() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [portfolioEquity, setPortfolioEquity] = useState(1000);
  const [modelsStatus, setModelsStatus] = useState({
    normal: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0 },
    runner: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0 },
  });

  useEffect(() => {
    const fetchStatus = () => {
      fetch(`${getApiBaseUrl()}/api/state`)
        .then((res) => res.json())
        .then((data) => {
          if (data.models_status) setModelsStatus(data.models_status);
          if (data.portfolio?.equity) setPortfolioEquity(data.portfolio.equity);
        })
        .catch((err) => console.error(err));
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

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
        body: JSON.stringify({ mode, type }),
      });
      const data = await res.json();
      toast.success(data.message, `${type.toUpperCase()} Training`);
    } catch {
      toast.error("Gagal memicu pelatihan model.", "Error");
    } finally {
      setLoading(false);
    }
  };

  const handleResetModels = async () => {
    if (!window.confirm("Konfirmasi Reset Model: Tindakan ini akan menghapus file model LightGBM (.pkl), membersihkan tabel hard_negatives, dan mengembalikan model ke status baseline baru (Untrained). Lanjutkan?")) {
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/reset-models`, {
        method: "POST",
      });
      const data = await res.json();
      toast.success(data.message, "Model Baseline Reset");
      setModelsStatus({
        normal: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0 },
        runner: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0 },
      });
    } catch {
      toast.error("Gagal mereset model ke baseline baru.", "Error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 md:p-8 flex flex-col h-full overflow-y-auto">
      {/* Page Header */}
      <div className="mb-6 shrink-0 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight flex items-center gap-3">
            <Settings2 className="text-brand-green w-7 h-7" />
            Strategies &amp; AI Incubator
          </h1>
          <p className="text-xs sm:text-sm text-white/50 mt-1">
            Manajemen risiko transaksi, pelatihan mandiri LightGBM, dan validasi kurasi RLHF
          </p>
        </div>
        <button
          onClick={handleResetModels}
          disabled={loading}
          className="self-start sm:self-auto px-4 py-2.5 rounded-xl text-xs font-bold text-amber-400 hover:text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 transition-all flex items-center gap-2 disabled:opacity-50"
          title="Hapus file .pkl lama, bersihkan hard_negatives, dan reset model ke baseline baru"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Reset Models &amp; Baseline
        </button>
      </div>

      {/* 1. Risk Management Card Component */}
      <RiskManagementCard portfolioEquity={portfolioEquity} />

      {/* 2. Model Status & Control Grid Component */}
      <ModelStatusGrid
        modelsStatus={modelsStatus}
        loading={loading}
        onTrain={handleTrainMode}
        onForceMode={handleForceMode}
      />

      {/* 3. RLHF Review Queue Component */}
      <RlhfReviewQueue />
    </div>
  );
}
