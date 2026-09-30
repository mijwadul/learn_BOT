"use client";

import { useState, useEffect } from "react";
import { Settings2 } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { RiskManagementCard } from "@/components/strategies/RiskManagementCard";
import { AiEntryThresholdCard } from "@/components/strategies/AiEntryThresholdCard";

export default function StrategiesPage() {
  const [portfolioEquity, setPortfolioEquity] = useState(1000);

  useEffect(() => {
    // Ambil equity portfolio untuk kalkulasi dinamis lot di RiskManagementCard
    fetch(`${getApiBaseUrl()}/api/state`)
      .then((res) => res.json())
      .then((data) => {
        if (data.portfolio?.equity) setPortfolioEquity(data.portfolio.equity);
      })
      .catch((err) => console.error("Error fetching state in strategies page:", err));
  }, []);

  return (
    <div className="p-4 sm:p-6 md:p-8 flex flex-col min-h-full">
      {/* Page Header */}
      <div className="mb-6 shrink-0">
        <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight flex items-center gap-3">
          <Settings2 className="text-brand-green w-7 h-7" />
          Strategies &amp; Risk Parameters
        </h1>
        <p className="text-xs sm:text-sm text-white/50 mt-1">
          Konfigurasi batas risiko portofolio (Dynamic Lot Sizing) dan ambang batas probabilitas AI Signal (Inference Threshold).
        </p>
      </div>

      {/* 1. Risk Management Card Component */}
      <RiskManagementCard portfolioEquity={portfolioEquity} />

      {/* 2. AI Signal Entry Threshold Card Component */}
      <AiEntryThresholdCard />
    </div>
  );
}
