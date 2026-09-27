"use client";

import React from "react";
import { Sliders, Plus, Trash2, Power } from "lucide-react";

interface PairItem {
  symbol: string;
  is_active: boolean;
  broker_symbol?: string;
}

interface DashboardHeaderProps {
  pairs: PairItem[];
  activeSymbol: string;
  setActiveSymbol: (sym: string) => void;
  handleTogglePair: (sym: string, currentActive: boolean) => void;
  handleRemovePair: (sym: string) => void;
  setShowAddPairModal: (show: boolean) => void;
  balance: number;
  equity: number;
  totalFloatingPnl: number;
  currentDrawdown: number;
  isNormalActive: boolean;
  isRunnerActive: boolean;
  isTogglingBrain: boolean;
  handleToggleBrain: (mode: "normal" | "runner" | "all", active: boolean) => void;
  isLive: boolean;
  toggleLive: () => void;
}

export const DashboardHeader: React.FC<DashboardHeaderProps> = ({
  pairs,
  activeSymbol,
  setActiveSymbol,
  handleTogglePair,
  handleRemovePair,
  setShowAddPairModal,
  balance,
  equity,
  totalFloatingPnl,
  currentDrawdown,
  isNormalActive,
  isRunnerActive,
  isTogglingBrain,
  handleToggleBrain,
  isLive,
  toggleLive,
}) => {
  return (
    <header className="px-3 sm:px-4 py-2 sm:py-2.5 border-b border-white/10 bg-black/60 backdrop-blur-md flex flex-wrap items-center justify-between shrink-0 gap-3 sm:gap-4">
      {/* Left: Multi-Pair Badges & Dynamic Switcher */}
      <div className="flex items-center gap-2 overflow-x-auto py-0.5 max-w-full custom-scrollbar">
        <span className="text-[11px] font-bold text-white/40 uppercase tracking-wider flex items-center gap-1.5 shrink-0 mr-1">
          <Sliders size={13} className="text-cyan-400" /> Pairs:
        </span>

        {(pairs.length > 0 ? pairs : [{ symbol: "XAUUSD", is_active: true }]).map((p) => {
          const isSelected = activeSymbol === p.symbol;
          return (
            <div
              key={p.symbol}
              onClick={() => setActiveSymbol(p.symbol)}
              className={`flex items-center rounded-xl border text-xs overflow-hidden transition-all duration-200 shrink-0 cursor-pointer ${
                isSelected
                  ? "border-cyan-400/80 bg-cyan-950/40 shadow-md shadow-cyan-500/20"
                  : "border-white/10 bg-white/[0.03] hover:border-white/20"
              }`}
            >
              <button
                type="button"
                onClick={() => setActiveSymbol(p.symbol)}
                className={`px-3 py-1.5 font-mono font-bold flex items-center gap-1.5 cursor-pointer ${
                  isSelected ? "text-cyan-300" : "text-white/70 hover:text-white"
                }`}
                title={`Tampilkan data telemetri AI untuk ${p.symbol}`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${p.is_active ? "bg-emerald-400 animate-pulse" : "bg-white/30"}`} />
                <span>{p.symbol}</span>
              </button>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleTogglePair(p.symbol, p.is_active);
                }}
                className={`px-2 py-1.5 text-[10px] font-black border-l transition-colors cursor-pointer ${
                  p.is_active
                    ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/30"
                    : "bg-white/5 text-white/40 border-white/10 hover:bg-white/10 hover:text-white/60"
                }`}
                title={p.is_active ? `Live trading AKTIF untuk ${p.symbol}. Klik untuk nonaktifkan.` : `Live trading NONAKTIF untuk ${p.symbol}. Klik untuk aktifkan.`}
              >
                {p.is_active ? "LIVE" : "OFF"}
              </button>

              {p.symbol !== "XAUUSD" && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRemovePair(p.symbol);
                  }}
                  className="px-1.5 py-1.5 text-white/30 hover:text-rose-400 hover:bg-rose-500/10 border-l border-white/10 transition-colors cursor-pointer"
                  title={`Hapus pair ${p.symbol}`}
                >
                  <Trash2 size={11} />
                </button>
              )}
            </div>
          );
        })}

        <button
          type="button"
          onClick={() => setShowAddPairModal(true)}
          className="px-2.5 py-1.5 rounded-xl border border-dashed border-white/20 hover:border-cyan-400/60 bg-white/[0.02] hover:bg-cyan-500/10 text-white/50 hover:text-cyan-300 text-xs font-semibold flex items-center gap-1 transition-all cursor-pointer shrink-0"
          title="Daftarkan pair baru ke sistem"
        >
          <Plus size={13} />
          <span>Tambah Pair</span>
        </button>
      </div>

      {/* Center: Financial Telemetry */}
      <div className="flex items-center gap-3 sm:gap-5 text-xs font-mono tabular-nums overflow-x-auto py-0.5 custom-scrollbar shrink-0">
        <div className="flex flex-col">
          <span className="text-[10px] text-white/40 uppercase font-semibold">Balance</span>
          <span className="font-bold text-white text-sm">${balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
        </div>

        <div className="h-6 w-px bg-white/10 hidden sm:block" />

        <div className="flex flex-col">
          <span className="text-[10px] text-white/40 uppercase font-semibold">Equity</span>
          <span className="font-bold text-white text-sm">${equity.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
        </div>

        <div className="h-6 w-px bg-white/10 hidden sm:block" />

        <div className="flex flex-col">
          <span className="text-[10px] text-white/40 uppercase font-semibold">Floating PnL</span>
          <span className={`font-bold text-sm ${totalFloatingPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {totalFloatingPnl >= 0 ? "+" : ""}${totalFloatingPnl.toFixed(2)}
          </span>
        </div>

        <div className="h-6 w-px bg-white/10 hidden sm:block" />

        <div className="flex flex-col">
          <span className="text-[10px] text-white/40 uppercase font-semibold">Sekring DD</span>
          <span className={`font-bold text-xs ${currentDrawdown > 15 ? "text-amber-400" : "text-emerald-400"}`}>
            {currentDrawdown.toFixed(1)}% <span className="text-white/40">/ 30%</span>
          </span>
        </div>
      </div>

      {/* Right: Master Bot & Otak Switch */}
      <div className="flex items-center gap-2 sm:gap-2.5 shrink-0 flex-wrap sm:flex-nowrap">
        <select
          value={
            isNormalActive && isRunnerActive
              ? "all"
              : isNormalActive
              ? "normal"
              : isRunnerActive
              ? "runner"
              : "none"
          }
          onChange={(e) => {
            const val = e.target.value;
            if (val === "all") handleToggleBrain("all", true);
            else if (val === "none") handleToggleBrain("all", false);
            else if (val === "normal") {
              handleToggleBrain("normal", true);
              handleToggleBrain("runner", false);
            } else if (val === "runner") {
              handleToggleBrain("runner", true);
              handleToggleBrain("normal", false);
            }
          }}
          disabled={isTogglingBrain}
          className="bg-black/60 border border-white/15 text-white/80 text-xs rounded-xl px-2.5 py-1.5 focus:ring-1 focus:ring-emerald-500 outline-none font-medium cursor-pointer"
          title="Pilih mode otak AI aktif"
        >
          <option value="all">🧠 Semua Otak (Scalp + Trend)</option>
          <option value="normal">⚡ Hanya Otak Scalp</option>
          <option value="runner">🚀 Hanya Otak Trend</option>
          <option value="none">🛑 Matikan Semua Otak</option>
        </select>

        <button
          type="button"
          onClick={toggleLive}
          className={`flex items-center justify-center gap-2 py-2 px-3.5 sm:px-4 rounded-xl transition-all duration-300 font-black text-xs sm:text-sm tracking-wider cursor-pointer shadow-lg ${
            isLive
              ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50 hover:bg-rose-500/30 shadow-rose-500/10'
              : 'bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold shadow-emerald-500/25'
          }`}
        >
          <Power size={15} className={isLive ? 'animate-pulse' : ''} />
          <span>{isLive ? 'STOP BOT' : 'START BOT'}</span>
        </button>
      </div>
    </header>
  );
};
