"use client";

import React from "react";
import { ShieldCheck, Scissors, XCircle } from "lucide-react";

interface Position {
  ticket: number;
  symbol: string;
  type: string;
  volume: number;
  open_price: number;
  current_price: number;
  sl?: number;
  tp?: number;
  profit: number;
}

interface OpenPositionsTableProps {
  openPositions: Position[];
  activeSymbol: string;
  actionLoadingTicket: { [ticket: number]: string };
  handlePositionAction: (ticket: number, action: "close" | "partial-close" | "break-even", symbol?: string) => void;
}

export const OpenPositionsTable: React.FC<OpenPositionsTableProps> = ({
  openPositions,
  activeSymbol,
  actionLoadingTicket,
  handlePositionAction,
}) => {
  if (openPositions.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center">
        <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-white/30 mb-3">
          <ShieldCheck size={24} className="text-emerald-400/60" />
        </div>
        <span className="text-sm font-semibold text-white/60">Tidak ada posisi terbuka</span>
      </div>
    );
  }

  return (
    <div className="w-full h-full overflow-y-auto custom-scrollbar">
      {/* Mobile Card Layout */}
      <div className="block md:hidden p-3 space-y-3">
        {openPositions.map((pos) => {
          const isBuy = pos.type === "BUY";
          const isProfit = pos.profit >= 0;
          const isLoading = !!actionLoadingTicket[pos.ticket];

          return (
            <div key={pos.ticket} className="bg-black/50 border border-white/10 rounded-xl p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-white/40 font-mono">#{pos.ticket}</span>
                  <span
                    className={`px-1.5 py-0.2 rounded border text-[10px] font-mono font-bold ${
                      (pos.symbol || activeSymbol).toUpperCase().includes("XAU")
                        ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                        : "bg-sky-500/15 text-sky-300 border-sky-500/30"
                    }`}
                  >
                    {pos.symbol || activeSymbol}
                  </span>
                  <span
                    className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                      isBuy ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                    }`}
                  >
                    {pos.type}
                  </span>
                </div>
                <span className={`text-xs font-bold font-mono ${isProfit ? "text-emerald-400" : "text-rose-400"}`}>
                  {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
                </span>
              </div>

              <div className="grid grid-cols-4 gap-1.5 text-[10px] pt-1.5 border-t border-white/5 font-mono text-white/60">
                <div>
                  <span className="text-white/30 block">Vol</span>
                  <span className="text-white/80 font-bold">{(pos.volume || 0).toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-white/30 block">Entry</span>
                  <span className="text-white/80">
                    {(pos.open_price || 0).toFixed((pos.open_price || 0) > 100 ? 2 : 5)}
                  </span>
                </div>
                <div>
                  <span className="text-white/30 block">Current</span>
                  <span className="text-white/90 font-bold">
                    {(pos.current_price || 0).toFixed((pos.current_price || 0) > 100 ? 2 : 5)}
                  </span>
                </div>
                <div>
                  <span className="text-white/30 block">SL/TP</span>
                  <span className="text-white/60">{pos.sl ? Number(pos.sl).toFixed(1) : "-"}</span>
                </div>
              </div>

              <div className="flex items-center gap-1.5 pt-1.5 border-t border-white/5">
                <button
                  type="button"
                  onClick={() => handlePositionAction(pos.ticket, "break-even", pos.symbol)}
                  disabled={isLoading}
                  className="flex-1 py-1 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold flex items-center justify-center gap-1 disabled:opacity-40 cursor-pointer"
                >
                  <ShieldCheck size={11} /> BE
                </button>
                <button
                  type="button"
                  onClick={() => handlePositionAction(pos.ticket, "partial-close", pos.symbol)}
                  disabled={isLoading}
                  className="flex-1 py-1 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-bold flex items-center justify-center gap-1 disabled:opacity-40 cursor-pointer"
                >
                  <Scissors size={11} /> 50%
                </button>
                <button
                  type="button"
                  onClick={() => handlePositionAction(pos.ticket, "close", pos.symbol)}
                  disabled={isLoading}
                  className="flex-1 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-[10px] font-bold flex items-center justify-center gap-1 disabled:opacity-40 cursor-pointer"
                >
                  <XCircle size={11} /> Close
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Desktop Table View */}
      <div className="hidden md:block">
        <table className="w-full text-left text-xs font-mono tabular-nums">
          <thead className="sticky top-0 bg-[#070b0a] border-b border-white/10 text-white/40 uppercase text-[10px] tracking-wider z-10">
            <tr>
              <th className="py-3 px-4">Ticket</th>
              <th className="py-3 px-4">Symbol</th>
              <th className="py-3 px-4">Type</th>
              <th className="py-3 px-4">Volume</th>
              <th className="py-3 px-4">Open Price</th>
              <th className="py-3 px-4">Current Price</th>
              <th className="py-3 px-4">SL / TP</th>
              <th className="py-3 px-4 text-right">Profit / Loss</th>
              <th className="py-3 px-4 text-center">Fast Action Guard</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {openPositions.map((pos) => {
              const isBuy = pos.type === "BUY";
              const isProfit = pos.profit >= 0;
              const isLoading = !!actionLoadingTicket[pos.ticket];

              return (
                <tr key={pos.ticket} className="hover:bg-white/[0.03] transition-colors">
                  <td className="py-3 px-4 text-white/40">#{pos.ticket}</td>
                  <td className="py-3 px-4 font-mono font-bold">
                    <span
                      className={`px-2 py-0.5 rounded-lg border text-xs font-mono font-bold ${
                        (pos.symbol || activeSymbol).toUpperCase().includes("XAU")
                          ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                          : "bg-sky-500/15 text-sky-300 border-sky-500/30"
                      }`}
                    >
                      {pos.symbol || activeSymbol}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        isBuy ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                      }`}
                    >
                      {pos.type}
                    </span>
                  </td>

                  <td className="py-3 px-4 text-white/80 font-bold">{(pos.volume || 0).toFixed(2)}</td>
                  <td className="py-3 px-4 text-white/80">
                    {(pos.open_price || 0).toFixed((pos.open_price || 0) > 100 ? 2 : 5)}
                  </td>
                  <td className="py-3 px-4 font-bold text-white">
                    {(pos.current_price || 0).toFixed((pos.current_price || 0) > 100 ? 2 : 5)}
                  </td>
                  <td className="py-3 px-4 text-white/60">
                    {pos.sl ? Number(pos.sl).toFixed((pos.sl || 0) > 100 ? 2 : 5) : "-"} /{" "}
                    {pos.tp ? Number(pos.tp).toFixed((pos.tp || 0) > 100 ? 2 : 5) : "-"}
                  </td>
                  <td
                    className={`py-3 px-4 text-right font-black text-sm ${
                      isProfit ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center justify-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => handlePositionAction(pos.ticket, "break-even", pos.symbol)}
                        disabled={isLoading}
                        title="Geser SL ke Break-Even (BE)"
                        className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                      >
                        <ShieldCheck size={12} /> BE
                      </button>
                      <button
                        type="button"
                        onClick={() => handlePositionAction(pos.ticket, "partial-close", pos.symbol)}
                        disabled={isLoading}
                        title="Tutup 50% Volume"
                        className="px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                      >
                        <Scissors size={12} /> 50%
                      </button>
                      <button
                        type="button"
                        onClick={() => handlePositionAction(pos.ticket, "close", pos.symbol)}
                        disabled={isLoading}
                        title="Tutup Posisi Penuh"
                        className="px-2.5 py-1 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                      >
                        <XCircle size={12} /> Close
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
