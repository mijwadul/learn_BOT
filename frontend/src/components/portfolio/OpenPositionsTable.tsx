"use client";

import React from "react";
import { ArrowUpRight, ArrowDownRight, Layers } from "lucide-react";

export interface Position {
  ticket: number;
  symbol: string;
  type: string;
  volume: number;
  open_price: number;
  current_price: number;
  profit: number;
}

interface OpenPositionsTableProps {
  positions: Position[];
}

export function OpenPositionsTable({ positions }: OpenPositionsTableProps) {
  return (
    <div className="flex-1 flex flex-col min-h-0 bg-[#0b1210] border border-white/10 rounded-2xl overflow-hidden shadow-xl">
      <div className="p-4 border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-brand-green" />
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">Open Positions</h3>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-white/5 text-white/60 border border-white/10">
          {positions.length} Active
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
            return (
              <div 
                key={pos.ticket}
                className="bg-white/[0.03] border border-white/10 rounded-xl p-3.5 flex flex-col gap-2"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-white/40 font-mono">#{pos.ticket}</span>
                    <span className="font-bold text-sm text-white">{pos.symbol}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      isBuy ? "bg-brand-green/20 text-brand-green" : "bg-brand-red/20 text-brand-red"
                    }`}>
                      {pos.type}
                    </span>
                  </div>
                  <div className={`text-sm font-black flex items-center gap-1 ${
                    isProfit ? "text-brand-green" : "text-brand-red"
                  }`}>
                    {isProfit ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                    {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 text-[11px] pt-2 border-t border-white/5 text-white/60">
                  <div>
                    <span className="text-white/30 block">Volume:</span>
                    <span className="font-semibold text-white/90">{pos.volume.toFixed(2)} Lot</span>
                  </div>
                  <div>
                    <span className="text-white/30 block">Open:</span>
                    <span className="font-semibold text-white/90">{pos.open_price.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-white/30 block">Current:</span>
                    <span className="font-semibold text-white/90">{pos.current_price.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Desktop Table View */}
      <div className="hidden md:flex flex-1 overflow-y-auto">
        <table className="w-full text-left">
          <thead className="sticky top-0 bg-[#070b0a] border-b border-white/10 text-white/50 text-xs uppercase tracking-wider z-10">
            <tr>
              <th className="p-4 font-semibold">Ticket</th>
              <th className="p-4 font-semibold">Symbol</th>
              <th className="p-4 font-semibold">Type</th>
              <th className="p-4 font-semibold">Volume</th>
              <th className="p-4 font-semibold">Open Price</th>
              <th className="p-4 font-semibold">Current Price</th>
              <th className="p-4 font-semibold text-right">Floating Profit</th>
            </tr>
          </thead>
          <tbody className="text-sm divide-y divide-white/5">
            {positions.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-8 text-center text-white/30 font-medium">
                  Tidak ada posisi trading yang sedang aktif saat ini.
                </td>
              </tr>
            ) : (
              positions.map((pos) => {
                const isBuy = pos.type === "BUY";
                const isProfit = pos.profit >= 0;
                return (
                  <tr key={pos.ticket} className="hover:bg-white/[0.03] transition-colors">
                    <td className="p-4 text-white/40 font-mono text-xs">#{pos.ticket}</td>
                    <td className="p-4 font-bold text-white">{pos.symbol}</td>
                    <td className="p-4">
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        isBuy ? "bg-brand-green/20 text-brand-green" : "bg-brand-red/20 text-brand-red"
                      }`}>
                        {pos.type}
                      </span>
                    </td>
                    <td className="p-4 text-white/80 font-mono">{pos.volume.toFixed(2)}</td>
                    <td className="p-4 text-white/80 font-mono">{pos.open_price.toFixed(2)}</td>
                    <td className="p-4 text-white/80 font-mono">{pos.current_price.toFixed(2)}</td>
                    <td className={`p-4 text-right font-black font-mono text-base ${
                      isProfit ? "text-brand-green" : "text-brand-red"
                    }`}>
                      {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
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
