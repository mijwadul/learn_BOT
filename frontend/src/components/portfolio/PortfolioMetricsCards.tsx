"use client";

import React from "react";
import { Wallet, Activity, ArrowUpRight, ArrowDownRight, Layers } from "lucide-react";

interface PortfolioMetricsCardsProps {
  balance: number;
  equity: number;
  openPositionsCount: number;
  floatingPnl: number;
}

export function PortfolioMetricsCards({
  balance,
  equity,
  openPositionsCount,
  floatingPnl,
}: PortfolioMetricsCardsProps) {
  const isProfit = floatingPnl >= 0;

  const formatCurrency = (val: number) => {
    return (val || 0).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {/* Balance Card */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl relative overflow-hidden group hover:border-brand-green/30 transition-all">
        <div className="flex items-center justify-between text-white/50 mb-3">
          <span className="text-xs font-bold uppercase tracking-wider">Account Balance</span>
          <div className="p-2 rounded-xl bg-white/5 group-hover:bg-brand-green/10 text-brand-green transition-colors">
            <Wallet size={18} />
          </div>
        </div>
        <div className="text-2xl sm:text-3xl font-black text-white tracking-tight">
          ${formatCurrency(balance)}
        </div>
        <p className="text-[11px] text-white/40 mt-1">Total modal terkunci di broker</p>
      </div>

      {/* Equity Card */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl relative overflow-hidden group hover:border-cyan-500/30 transition-all">
        <div className="flex items-center justify-between text-white/50 mb-3">
          <span className="text-xs font-bold uppercase tracking-wider">Floating Equity</span>
          <div className="p-2 rounded-xl bg-white/5 group-hover:bg-cyan-500/10 text-cyan-400 transition-colors">
            <Activity size={18} />
          </div>
        </div>
        <div className="text-2xl sm:text-3xl font-black text-white tracking-tight">
          ${formatCurrency(equity)}
        </div>
        <p className="text-[11px] text-white/40 mt-1">Nilai kas jika posisi ditutup saat ini</p>
      </div>

      {/* Floating PnL Card */}
      <div className={`bg-[#0b1210] border rounded-2xl p-5 shadow-xl relative overflow-hidden transition-all ${
        isProfit ? "border-brand-green/30 bg-brand-green/5" : "border-brand-red/30 bg-brand-red/5"
      }`}>
        <div className="flex items-center justify-between text-white/50 mb-3">
          <span className="text-xs font-bold uppercase tracking-wider">Floating PnL</span>
          <div className={`p-2 rounded-xl ${isProfit ? "bg-brand-green/20 text-brand-green" : "bg-brand-red/20 text-brand-red"}`}>
            {isProfit ? <ArrowUpRight size={18} /> : <ArrowDownRight size={18} />}
          </div>
        </div>
        <div className={`text-2xl sm:text-3xl font-black tracking-tight ${
          isProfit ? "text-brand-green" : "text-brand-red"
        }`}>
          {isProfit ? "+" : ""}${formatCurrency(floatingPnl)}
        </div>
        <p className="text-[11px] text-white/40 mt-1">Keuntungan / kerugian berjalan</p>
      </div>

      {/* Active Positions Count Card */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl relative overflow-hidden group hover:border-amber-500/30 transition-all">
        <div className="flex items-center justify-between text-white/50 mb-3">
          <span className="text-xs font-bold uppercase tracking-wider">Active Deals</span>
          <div className="p-2 rounded-xl bg-white/5 group-hover:bg-amber-500/10 text-amber-400 transition-colors">
            <Layers size={18} />
          </div>
        </div>
        <div className="text-2xl sm:text-3xl font-black text-white tracking-tight">
          {openPositionsCount} <span className="text-sm font-semibold text-white/40">Posisi</span>
        </div>
        <p className="text-[11px] text-white/40 mt-1">Total lot terbuka di pasar aktif</p>
      </div>
    </div>
  );
}
