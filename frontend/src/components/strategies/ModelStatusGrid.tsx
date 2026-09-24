"use client";

import React from "react";
import { BrainCircuit, Loader2, Zap, ShieldAlert } from "lucide-react";

interface ModelInfo {
  trained: boolean;
  status: string;
  is_training: boolean;
  last_accuracy: number;
}

interface ModelStatusGridProps {
  modelsStatus: {
    normal: ModelInfo;
    runner: ModelInfo;
  };
  loading: boolean;
  onTrain: (mode: string, type: "incremental" | "full") => void;
  onForceMode: (mode: string, action: "force_live" | "quarantine") => void;
}

export function ModelStatusGrid({
  modelsStatus,
  loading,
  onTrain,
  onForceMode,
}: ModelStatusGridProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6 mb-6 md:mb-8 shrink-0">
      {/* Normal Mode */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg sm:text-xl font-bold text-white">Normal Mode (Scalping 1:2)</h2>
            <div className="flex items-center gap-1.5 text-xs font-bold">
              <span className={`px-2.5 py-0.5 rounded-full ${
                modelsStatus.normal.trained ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30" : "bg-white/10 text-white/50"
              }`}>
                {modelsStatus.normal.trained ? "TRAINED" : "UNTRAINED"}
              </span>
              <span className={`px-2.5 py-0.5 rounded-full ${
                modelsStatus.normal.status.includes("LIVE") ? "bg-brand-green/20 text-brand-green border border-brand-green/30" : "bg-brand-red/20 text-brand-red border border-brand-red/30"
              }`}>
                {modelsStatus.normal.status}
              </span>
            </div>
          </div>
          <p className="text-xs sm:text-sm text-white/50 mb-3">
            Intraday scalping BBMA Re-entry berpedoman pada RR pas 1:2 dengan pelindung BE pada 1R.
          </p>
          {modelsStatus.normal.trained && (
            <div className="mb-4 inline-block">
              <span className={`px-3 py-1 rounded-xl text-xs font-bold border ${
                modelsStatus.normal.last_accuracy >= 0.50
                  ? "bg-brand-green/10 text-brand-green border-brand-green/30"
                  : "bg-amber-500/10 text-amber-400 border-amber-500/30"
              }`}>
                OOS Validation Score: {(modelsStatus.normal.last_accuracy * 100).toFixed(1)}%
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2.5 pt-2">
          <div className="grid grid-cols-2 gap-2.5">
            <button
              disabled={loading || modelsStatus.normal.is_training}
              onClick={() => onTrain("normal", "incremental")}
              className="bg-brand-blue/20 hover:bg-brand-blue/30 text-brand-blue border border-brand-blue/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs disabled:opacity-50"
            >
              {modelsStatus.normal.is_training ? (
                <><Loader2 className="animate-spin w-4 h-4" /> Training...</>
              ) : (
                <><BrainCircuit size={15} /> Incremental Train</>
              )}
            </button>
            <button
              disabled={loading || modelsStatus.normal.is_training}
              onClick={() => onTrain("normal", "full")}
              className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs disabled:opacity-50"
            >
              {modelsStatus.normal.is_training ? (
                <><Loader2 className="animate-spin w-4 h-4" /> Training...</>
              ) : (
                "Force Full Train"
              )}
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <button
              disabled={loading}
              onClick={() => onForceMode("normal", "force_live")}
              className="bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs"
            >
              <Zap size={16} /> Force LIVE
            </button>
            <button
              disabled={loading}
              onClick={() => onForceMode("normal", "quarantine")}
              className="bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs"
            >
              <ShieldAlert size={16} /> Quarantine
            </button>
          </div>
        </div>
      </div>

      {/* Runner Mode */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl flex flex-col justify-between">
        <div>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-lg sm:text-xl font-bold text-white">Runner Mode (Trend Exploitation)</h2>
            <div className="flex items-center gap-1.5 text-xs font-bold">
              <span className={`px-2.5 py-0.5 rounded-full ${
                modelsStatus.runner.trained ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30" : "bg-white/10 text-white/50"
              }`}>
                {modelsStatus.runner.trained ? "TRAINED" : "UNTRAINED"}
              </span>
              <span className={`px-2.5 py-0.5 rounded-full ${
                modelsStatus.runner.status.includes("LIVE") ? "bg-brand-green/20 text-brand-green border border-brand-green/30" : "bg-brand-red/20 text-brand-red border border-brand-red/30"
              }`}>
                {modelsStatus.runner.status}
              </span>
            </div>
          </div>
          <p className="text-xs sm:text-sm text-white/50 mb-3">
            Trend-following dinamis dengan milestone partial close 50% di 2R dan target hingga 5R.
          </p>
          {modelsStatus.runner.trained && (
            <div className="mb-4 inline-block">
              <span className={`px-3 py-1 rounded-xl text-xs font-bold border ${
                modelsStatus.runner.last_accuracy >= 0.50
                  ? "bg-brand-green/10 text-brand-green border-brand-green/30"
                  : "bg-amber-500/10 text-amber-400 border-amber-500/30"
              }`}>
                OOS Validation Score: {(modelsStatus.runner.last_accuracy * 100).toFixed(1)}%
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-2.5 pt-2">
          <div className="grid grid-cols-2 gap-2.5">
            <button
              disabled={loading || modelsStatus.runner.is_training}
              onClick={() => onTrain("runner", "incremental")}
              className="bg-brand-blue/20 hover:bg-brand-blue/30 text-brand-blue border border-brand-blue/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs disabled:opacity-50"
            >
              {modelsStatus.runner.is_training ? (
                <><Loader2 className="animate-spin w-4 h-4" /> Training...</>
              ) : (
                <><BrainCircuit size={15} /> Incremental Train</>
              )}
            </button>
            <button
              disabled={loading || modelsStatus.runner.is_training}
              onClick={() => onTrain("runner", "full")}
              className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs disabled:opacity-50"
            >
              {modelsStatus.runner.is_training ? (
                <><Loader2 className="animate-spin w-4 h-4" /> Training...</>
              ) : (
                "Force Full Train"
              )}
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <button
              disabled={loading}
              onClick={() => onForceMode("runner", "force_live")}
              className="bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs"
            >
              <Zap size={16} /> Force LIVE
            </button>
            <button
              disabled={loading}
              onClick={() => onForceMode("runner", "quarantine")}
              className="bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs"
            >
              <ShieldAlert size={16} /> Quarantine
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
