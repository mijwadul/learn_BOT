"use client";

import { useState, useEffect } from "react";
import { RotateCcw } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { PortfolioMetricsCards } from "@/components/portfolio/PortfolioMetricsCards";
import { OpenPositionsTable } from "@/components/portfolio/OpenPositionsTable";
import { FreshStartModal } from "@/components/portfolio/FreshStartModal";

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState({ value: 0, equity: 0, open_positions: [] as any[] });
  const [showModal, setShowModal] = useState(false);

  const fetchPortfolio = () => {
    fetch(`${getApiBaseUrl()}/api/state`)
      .then((res) => res.json())
      .then((data) => {
        if (data.portfolio) {
          setPortfolio({
            ...data.portfolio,
            open_positions: data.open_positions || [],
          });
        }
      })
      .catch((err) => console.error("Backend offline", err));
  };

  useEffect(() => {
    fetchPortfolio();
    const interval = setInterval(fetchPortfolio, 3000);
    return () => clearInterval(interval);
  }, []);

  const totalFloatingPnl = portfolio.open_positions.reduce((acc, pos) => acc + (pos.profit || 0), 0);

  return (
    <div className="p-4 sm:p-6 md:p-8 flex flex-col h-full overflow-y-auto">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
        <div>
          <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight">Portfolio & Deals</h2>
          <p className="text-xs sm:text-sm text-white/50 mt-0.5">
            Manajemen saldo ekuitas akun dan pemantauan posisi aktif MT5
          </p>
        </div>

        {/* Fresh Start Button */}
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm font-bold text-red-300 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 transition-all shadow-lg shadow-red-950/20"
        >
          <RotateCcw size={16} />
          Fresh Start (Drop Data)
        </button>
      </div>

      {/* Portfolio KPI Metrics Cards */}
      <PortfolioMetricsCards
        balance={portfolio.value}
        equity={portfolio.equity}
        openPositionsCount={portfolio.open_positions.length}
        floatingPnl={totalFloatingPnl}
      />

      {/* Open Positions List / Table */}
      <OpenPositionsTable positions={portfolio.open_positions} onActionSuccess={fetchPortfolio} />

      {/* Fresh Start Modal Component */}
      <FreshStartModal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        onSuccess={fetchPortfolio}
      />
    </div>
  );
}
