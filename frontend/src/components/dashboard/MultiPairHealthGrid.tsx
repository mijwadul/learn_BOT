"use client";

import React from "react";

interface PairHealth {
  symbol: string;
  broker_symbol?: string;
  is_active: boolean;
  table_name?: string;
  row_count?: number;
  has_normal_model?: boolean;
  last_accuracy_normal?: number;
  has_runner_model?: boolean;
  last_accuracy_runner?: number;
}

interface MultiPairHealthGridProps {
  pairs: PairHealth[];
  handleTogglePair: (symbol: string, currentActive: boolean) => void;
  handleRemovePair: (symbol: string) => void;
}

export const MultiPairHealthGrid: React.FC<MultiPairHealthGridProps> = ({
  pairs,
  handleTogglePair,
  handleRemovePair,
}) => {
  return (
    <div className="w-full h-full overflow-y-auto custom-scrollbar p-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {pairs.map((p) => (
          <div key={p.symbol} className="bg-black/40 border border-white/10 rounded-2xl p-4 flex flex-col justify-between gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-base font-bold font-mono text-white">{p.symbol}</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-white/50 font-mono">
                  Broker: {p.broker_symbol || p.symbol}
                </span>
              </div>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  p.is_active ? "bg-emerald-500/20 text-emerald-400" : "bg-white/10 text-white/40"
                }`}
              >
                {p.is_active ? "LIVE ACTIVE" : "OFF"}
              </span>
            </div>

            <div className="space-y-1.5 text-xs font-mono">
              <div className="flex justify-between text-white/60">
                <span>Candles Tersimpan:</span>
                <span className="text-cyan-300 font-bold">{p.row_count?.toLocaleString() || 0}</span>
              </div>
              <div className="flex justify-between text-white/60">
                <span>Normal Model:</span>
                <span className={p.has_normal_model ? "text-emerald-400 font-bold" : "text-white/30"}>
                  {p.has_normal_model ? `Trained (${((p.last_accuracy_normal || 0) * 100).toFixed(1)}%)` : "Not Trained"}
                </span>
              </div>
              <div className="flex justify-between text-white/60">
                <span>Runner Model:</span>
                <span className={p.has_runner_model ? "text-purple-400 font-bold" : "text-white/30"}>
                  {p.has_runner_model ? `Trained (${((p.last_accuracy_runner || 0) * 100).toFixed(1)}%)` : "Not Trained"}
                </span>
              </div>
            </div>

            <div className="pt-2 border-t border-white/5 flex items-center justify-between">
              <button
                type="button"
                onClick={() => handleTogglePair(p.symbol, p.is_active)}
                className={`text-xs font-bold px-3 py-1 rounded-xl transition-all cursor-pointer ${
                  p.is_active
                    ? "bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30"
                    : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                }`}
              >
                {p.is_active ? "Nonaktifkan" : "Aktifkan Trading"}
              </button>
              {p.symbol !== "XAUUSD" && (
                <button
                  type="button"
                  onClick={() => handleRemovePair(p.symbol)}
                  className="text-xs text-white/30 hover:text-rose-400 transition-colors cursor-pointer"
                >
                  Hapus Pair
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
