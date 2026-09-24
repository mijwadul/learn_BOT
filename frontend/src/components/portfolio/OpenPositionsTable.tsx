"use client";

import React, { useState } from "react";
import { ArrowUpRight, ArrowDownRight, Layers, ShieldCheck, Scissors, XCircle, Loader2 } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";

export interface Position {
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
  positions: Position[];
  onActionSuccess?: () => void;
}

export function OpenPositionsTable({ positions, onActionSuccess }: OpenPositionsTableProps) {
  const toast = useToast();
  const [activeActionTicket, setActiveActionTicket] = useState<{ [ticket: number]: string }>({});

  const handleAction = async (ticket: number, actionType: "break-even" | "partial-close" | "close", symbol: string) => {
    setActiveActionTicket((prev) => ({ ...prev, [ticket]: actionType }));
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/positions/${actionType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket, symbol }),
      });
      const data = await res.json();
      if (data.status === "success") {
        if (actionType === "break-even") toast.success(`Tiket #${ticket} Stop Loss berhasil digeser ke Break-Even (BE).`, "SL Protected");
        if (actionType === "partial-close") toast.success(`Tiket #${ticket} berhasil Partial Close 50% volume.`, "50% Closed");
        if (actionType === "close") toast.info(`Tiket #${ticket} telah dilikuidasi penuh.`, "Trade Closed");
        if (onActionSuccess) onActionSuccess();
      } else {
        toast.error(`Gagal mengeksekusi ${actionType} untuk tiket #${ticket}.`, "Gagal Eksekusi");
      }
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Koneksi Error");
    } finally {
      setActiveActionTicket((prev) => {
        const next = { ...prev };
        delete next[ticket];
        return next;
      });
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[#0b1210] border border-white/10 rounded-2xl overflow-hidden shadow-xl">
      <div className="p-4 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-brand-green" />
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Live Position Blotter</h3>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-white/5 text-white/70 border border-white/10 tabular-nums font-mono">
          {positions.length} Active Positions
        </span>
      </div>

      {/* Mobile Card View */}
      <div className="md:hidden flex-1 overflow-y-auto p-3 space-y-3">
        {positions.length === 0 ? (
          <div className="p-8 text-center text-white/30 text-xs font-medium">
            Tidak ada posisi yang terbuka saat ini.
          </div>
        ) : (
          positions.map((pos) => {
            const isBuy = pos.type === "BUY";
            const isProfit = pos.profit >= 0;
            const isLoading = !!activeActionTicket[pos.ticket];

            return (
              <div 
                key={pos.ticket}
                className="bg-white/[0.03] border border-white/10 rounded-xl p-3.5 flex flex-col gap-2.5"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-white/40 font-mono tabular-nums">#{pos.ticket}</span>
                    <span className="font-bold text-sm text-white">{pos.symbol}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      isBuy ? "bg-brand-green/20 text-brand-green" : "bg-brand-red/20 text-brand-red"
                    }`}>
                      {pos.type}
                    </span>
                  </div>
                  <div className={`text-sm font-black flex items-center gap-1 font-mono tabular-nums ${
                    isProfit ? "text-brand-green" : "text-brand-red"
                  }`}>
                    {isProfit ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                    {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-2 text-[11px] pt-2 border-t border-white/5 text-white/60 font-mono tabular-nums">
                  <div>
                    <span className="text-white/30 block text-[10px]">Vol</span>
                    <span className="font-semibold text-white/90">{pos.volume.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-white/30 block text-[10px]">Entry</span>
                    <span className="font-semibold text-white/90">{pos.open_price.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-white/30 block text-[10px]">Current</span>
                    <span className="font-semibold text-white/90">{pos.current_price.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-white/30 block text-[10px]">SL / TP</span>
                    <span className="font-semibold text-white/70">{pos.sl ? pos.sl.toFixed(1) : "-"} / {pos.tp ? pos.tp.toFixed(1) : "-"}</span>
                  </div>
                </div>

                {/* Mobile Quick Actions */}
                <div className="flex items-center gap-2 pt-1 border-t border-white/5">
                  <button
                    onClick={() => handleAction(pos.ticket, "break-even", pos.symbol)}
                    disabled={isLoading}
                    className="flex-1 py-1.5 px-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded-lg text-[10px] font-bold flex items-center justify-center gap-1 transition-all disabled:opacity-50"
                  >
                    <ShieldCheck size={12} />
                    BE
                  </button>
                  <button
                    onClick={() => handleAction(pos.ticket, "partial-close", pos.symbol)}
                    disabled={isLoading}
                    className="flex-1 py-1.5 px-2 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-lg text-[10px] font-bold flex items-center justify-center gap-1 transition-all disabled:opacity-50"
                  >
                    <Scissors size={12} />
                    50%
                  </button>
                  <button
                    onClick={() => handleAction(pos.ticket, "close", pos.symbol)}
                    disabled={isLoading}
                    className="flex-1 py-1.5 px-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 rounded-lg text-[10px] font-bold flex items-center justify-center gap-1 transition-all disabled:opacity-50"
                  >
                    <XCircle size={12} />
                    Close
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Desktop Table View */}
      <div className="hidden md:flex flex-1 overflow-y-auto">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-[#070b0a] border-b border-white/10 text-white/50 text-[11px] uppercase tracking-wider z-10">
            <tr>
              <th className="py-3 px-4 font-semibold">Ticket</th>
              <th className="py-3 px-4 font-semibold">Symbol</th>
              <th className="py-3 px-4 font-semibold">Type</th>
              <th className="py-3 px-4 font-semibold">Volume</th>
              <th className="py-3 px-4 font-semibold">Open Price</th>
              <th className="py-3 px-4 font-semibold">Current Price</th>
              <th className="py-3 px-4 font-semibold">Stop Loss</th>
              <th className="py-3 px-4 font-semibold">Take Profit</th>
              <th className="py-3 px-4 font-semibold text-right">Floating PnL</th>
              <th className="py-3 px-4 font-semibold text-center">Quick Actions</th>
            </tr>
          </thead>
          <tbody className="text-xs divide-y divide-white/5 font-mono tabular-nums">
            {positions.length === 0 ? (
              <tr>
                <td colSpan={10} className="p-8 text-center text-white/30 font-medium">
                  Tidak ada posisi trading yang sedang aktif saat ini.
                </td>
              </tr>
            ) : (
              positions.map((pos) => {
                const isBuy = pos.type === "BUY";
                const isProfit = pos.profit >= 0;
                const isLoading = !!activeActionTicket[pos.ticket];

                return (
                  <tr key={pos.ticket} className="hover:bg-white/[0.03] transition-colors">
                    <td className="py-3.5 px-4 text-white/40 text-xs">#{pos.ticket}</td>
                    <td className="py-3.5 px-4 font-bold text-white">{pos.symbol}</td>
                    <td className="py-3.5 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        isBuy ? "bg-brand-green/20 text-brand-green" : "bg-brand-red/20 text-brand-red"
                      }`}>
                        {pos.type}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-white/80">{pos.volume.toFixed(2)}</td>
                    <td className="py-3.5 px-4 text-white/80">{pos.open_price.toFixed(2)}</td>
                    <td className="py-3.5 px-4 text-white/90 font-semibold">{pos.current_price.toFixed(2)}</td>
                    <td className="py-3.5 px-4 text-rose-400/80">{pos.sl ? pos.sl.toFixed(2) : "-"}</td>
                    <td className="py-3.5 px-4 text-emerald-400/80">{pos.tp ? pos.tp.toFixed(2) : "-"}</td>
                    <td className={`py-3.5 px-4 text-right font-black text-sm ${
                      isProfit ? "text-brand-green" : "text-brand-red"
                    }`}>
                      {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="flex items-center justify-center gap-1.5">
                        <button
                          onClick={() => handleAction(pos.ticket, "break-even", pos.symbol)}
                          disabled={isLoading}
                          title="Geser SL ke Break-Even (+0.10 buffer)"
                          className="px-2 py-1 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                        >
                          {isLoading && activeActionTicket[pos.ticket] === "break-even" ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : (
                            <ShieldCheck size={11} />
                          )}
                          BE
                        </button>
                        <button
                          onClick={() => handleAction(pos.ticket, "partial-close", pos.symbol)}
                          disabled={isLoading}
                          title="Tutup 50% Lot (Partial Take Profit)"
                          className="px-2 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                        >
                          {isLoading && activeActionTicket[pos.ticket] === "partial-close" ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : (
                            <Scissors size={11} />
                          )}
                          50%
                        </button>
                        <button
                          onClick={() => handleAction(pos.ticket, "close", pos.symbol)}
                          disabled={isLoading}
                          title="Tutup Seluruh Posisi Sekarang"
                          className="px-2 py-1 bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                        >
                          {isLoading && activeActionTicket[pos.ticket] === "close" ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : (
                            <XCircle size={11} />
                          )}
                          Close
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
