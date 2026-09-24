"use client";

import { useState, useEffect } from "react";
import { Settings2 } from "lucide-react";
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

  return (
    <div className="p-4 sm:p-6 md:p-8 flex flex-col h-full overflow-y-auto">
      {/* Page Header */}
      <div className="mb-6 shrink-0">
        <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight flex items-center gap-3">
          <Settings2 className="text-brand-green w-7 h-7" />
          Strategies &amp; AI Incubator
        </h1>
        <p className="text-xs sm:text-sm text-white/50 mt-1">
          Manajemen risiko transaksi, pelatihan mandiri LightGBM, dan validasi kurasi RLHF
        </p>
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
