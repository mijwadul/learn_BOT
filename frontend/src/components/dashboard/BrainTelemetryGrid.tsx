"use client";

import React from "react";
import { Sparkles, Brain, Activity, RefreshCw, ShieldAlert, CheckCircle2 } from "lucide-react";
import NewsCountdown, { MacroEvent } from "@/components/NewsCountdown";

interface BrainTelemetryGridProps {
  activeSymbol: string;
  allBrainsActive: boolean;
  isNormalActive: boolean;
  isRunnerActive: boolean;
  isTogglingBrain: boolean;
  handleToggleBrain: (mode: "normal" | "runner" | "all", active: boolean) => void;
  normalBuyProb: number;
  normalSellProb: number;
  runnerBuyProb: number;
  runnerSellProb: number;
  dominantDirection: string;
  marketRegime: { adx: number; regime: string };
  onlineLearning: { enabled: boolean; last_retrain: string | null };
  handleTriggerMicroRetrain: () => void;
  isMicroRetraining: boolean;
  nextNews: MacroEvent | null;
}

export const BrainTelemetryGrid: React.FC<BrainTelemetryGridProps> = ({
  activeSymbol,
  allBrainsActive,
  isNormalActive,
  isRunnerActive,
  isTogglingBrain,
  handleToggleBrain,
  normalBuyProb,
  normalSellProb,
  runnerBuyProb,
  runnerSellProb,
  dominantDirection,
  marketRegime,
  onlineLearning,
  handleTriggerMicroRetrain,
  isMicroRetraining,
  nextNews,
}) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4 shrink-0">
      {/* Card 1: AI Confidence Radar (Dual-Target LightGBM) with Brain Controls */}
      <div className="rounded-2xl border border-white/10 bg-[#090e0c]/90 backdrop-blur-md p-4 flex flex-col justify-between shadow-xl">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-1.5">
            <Sparkles size={14} className="text-cyan-400" /> AI Confidence &amp; Otak
          </span>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
              {activeSymbol}
            </span>
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${
                allBrainsActive
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                  : isNormalActive || isRunnerActive
                  ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                  : "bg-rose-500/20 text-rose-400 border-rose-500/30"
              }`}
            >
              {allBrainsActive ? "ALL ON" : isNormalActive || isRunnerActive ? "PARTIAL" : "ALL OFF"}
            </span>
          </div>
        </div>

        <div className="space-y-2.5 font-mono tabular-nums">
          {/* Scalp Normal Confidence + Otak Toggle */}
          <div
            className={`p-2.5 rounded-xl border transition-all ${
              isNormalActive ? "bg-black/60 border-emerald-500/30" : "bg-black/40 border-white/5 opacity-70"
            }`}
          >
            <div className="flex justify-between items-center text-xs mb-1.5">
              <div className="flex items-center gap-2">
                <span className="font-sans font-bold text-white/90">Normal Scalp</span>
                <button
                  type="button"
                  onClick={() => handleToggleBrain("normal", !isNormalActive)}
                  disabled={isTogglingBrain}
                  title={isNormalActive ? "Otak Scalp LIVE. Klik untuk nonaktifkan." : "Otak Scalp OFF. Klik untuk aktifkan."}
                  className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider transition-all cursor-pointer flex items-center gap-1 ${
                    isNormalActive
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 shadow-sm shadow-emerald-500/20 hover:bg-emerald-500/30"
                      : "bg-white/10 text-white/40 border border-white/10 hover:text-white hover:bg-white/20"
                  }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${isNormalActive ? "bg-emerald-400 animate-pulse" : "bg-white/30"}`} />
                  <span>{isNormalActive ? "LIVE" : "OFF"}</span>
                </button>
              </div>
              <span className="text-cyan-300 font-bold">{Math.max(normalBuyProb, normalSellProb)}%</span>
            </div>
            <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden flex">
              <div
                className="bg-emerald-400 h-full transition-all duration-500"
                style={{ width: `${normalBuyProb}%` }}
                title={`Buy: ${normalBuyProb}%`}
              />
              <div
                className="bg-rose-500 h-full transition-all duration-500"
                style={{ width: `${normalSellProb}%` }}
                title={`Sell: ${normalSellProb}%`}
              />
            </div>
            <div className="flex justify-between text-[10px] text-white/40 mt-1">
              <span className="text-emerald-400/80">BUY: {normalBuyProb}%</span>
              <span className="text-rose-400/80">SELL: {normalSellProb}%</span>
            </div>
          </div>

          {/* Trend Runner Confidence + Otak Toggle */}
          <div
            className={`p-2.5 rounded-xl border transition-all ${
              isRunnerActive ? "bg-black/60 border-purple-500/30" : "bg-black/40 border-white/5 opacity-70"
            }`}
          >
            <div className="flex justify-between items-center text-xs mb-1.5">
              <div className="flex items-center gap-2">
                <span className="font-sans font-bold text-white/90">Runner Trend</span>
                <button
                  type="button"
                  onClick={() => handleToggleBrain("runner", !isRunnerActive)}
                  disabled={isTogglingBrain}
                  title={isRunnerActive ? "Otak Trend LIVE. Klik untuk nonaktifkan." : "Otak Trend OFF. Klik untuk aktifkan."}
                  className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider transition-all cursor-pointer flex items-center gap-1 ${
                    isRunnerActive
                      ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-sm shadow-purple-500/20 hover:bg-purple-500/30"
                      : "bg-white/10 text-white/40 border border-white/10 hover:text-white hover:bg-white/20"
                  }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${isRunnerActive ? "bg-purple-400 animate-pulse" : "bg-white/30"}`} />
                  <span>{isRunnerActive ? "LIVE" : "OFF"}</span>
                </button>
              </div>
              <span className="text-purple-300 font-bold">{Math.max(runnerBuyProb, runnerSellProb)}%</span>
            </div>
            <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden flex">
              <div
                className="bg-emerald-400 h-full transition-all duration-500"
                style={{ width: `${runnerBuyProb}%` }}
                title={`Buy: ${runnerBuyProb}%`}
              />
              <div
                className="bg-rose-500 h-full transition-all duration-500"
                style={{ width: `${runnerSellProb}%` }}
                title={`Sell: ${runnerSellProb}%`}
              />
            </div>
            <div className="flex justify-between text-[10px] text-white/40 mt-1">
              <span className="text-emerald-400/80">BUY: {runnerBuyProb}%</span>
              <span className="text-rose-400/80">SELL: {runnerSellProb}%</span>
            </div>
          </div>
        </div>

        {/* AI Consensus & Master Brain Controls */}
        <div className="mt-2.5 pt-2 border-t border-white/5 flex flex-col gap-2">
          <div className="flex items-center justify-between text-[11px]">
            <span className="text-white/40">AI Consensus:</span>
            <span
              className={`font-bold px-2 py-0.5 rounded text-[10px] tracking-wider ${
                dominantDirection === "BUY"
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : dominantDirection === "SELL"
                  ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                  : "bg-white/5 text-white/50 border border-white/10"
              }`}
            >
              {dominantDirection}
            </span>
          </div>

          <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[11px]">
            <span className="text-white/40 text-[10px] uppercase font-bold flex items-center gap-1">
              <Brain size={12} className="text-brand-green" /> Saklar Otak:
            </span>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => handleToggleBrain("all", true)}
                disabled={isTogglingBrain}
                title="Aktifkan seluruh otak (Scalp 1:2 &amp; Trend 1:5)"
                className="px-2 py-0.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 text-[10px] font-bold transition-all cursor-pointer"
              >
                Semua ON
              </button>
              <button
                type="button"
                onClick={() => handleToggleBrain("all", false)}
                disabled={isTogglingBrain}
                title="Nonaktifkan seluruh otak (Quarantine)"
                className="px-2 py-0.5 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 border border-rose-500/30 text-[10px] font-bold transition-all cursor-pointer"
              >
                Semua OFF
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Card 2: Market Topography & ADX Regime Sensor */}
      <div className="rounded-2xl border border-white/10 bg-[#090e0c]/90 backdrop-blur-md p-4 flex flex-col justify-between shadow-xl">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-1.5">
            <Activity size={14} className="text-indigo-400" /> Market Regime
          </span>
          <span className="text-[10px] font-mono text-white/40">ADX Filter</span>
        </div>

        <div className="space-y-3">
          <div className="bg-black/40 p-3 rounded-xl border border-white/5 flex items-center justify-between">
            <div>
              <span className="text-[10px] text-white/40 uppercase font-semibold block">Regime Deteksi</span>
              <span className="text-sm font-bold text-white tracking-wide">{marketRegime.regime}</span>
            </div>
            <div className="text-right font-mono">
              <span className="text-[10px] text-white/40 uppercase font-semibold block">ADX Value</span>
              <span className="text-base font-black text-indigo-300">{marketRegime.adx.toFixed(1)}</span>
            </div>
          </div>

          <div className="space-y-1.5 text-xs">
            <div className="flex items-center justify-between text-white/60">
              <span>Routing Aturan:</span>
              <span className="font-bold text-white/80">
                {marketRegime.adx >= 25 ? "Prioritaskan Runner (Trend)" : "Prioritaskan Scalp (Range)"}
              </span>
            </div>
            <div className="flex items-center justify-between text-white/60">
              <span>Online Learning:</span>
              <span className="font-mono text-emerald-400">
                {onlineLearning.enabled ? "Active (1 Jam)" : "Standby"}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-2.5 pt-2 border-t border-white/5 flex items-center justify-between">
          <span className="text-[10px] text-white/40 font-mono">
            Last Retrain: {onlineLearning.last_retrain ? onlineLearning.last_retrain.substring(11, 16) : "Ready"}
          </span>
          <button
            type="button"
            onClick={handleTriggerMicroRetrain}
            disabled={isMicroRetraining}
            className="text-[10px] font-bold px-2 py-0.5 rounded bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/40 flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
          >
            <RefreshCw size={10} className={isMicroRetraining ? "animate-spin" : ""} />
            <span>Micro-Retrain</span>
          </button>
        </div>
      </div>

      {/* Card 3: Macro Intelligence & High-Impact News Radar */}
      <div className="rounded-2xl border border-white/10 bg-[#090e0c]/90 backdrop-blur-md p-4 flex flex-col justify-between shadow-xl">
        <NewsCountdown initialEvent={nextNews} />
      </div>

      {/* Card 4: Institutional Risk & Circuit Breaker Health */}
      <div className="rounded-2xl border border-white/10 bg-[#090e0c]/90 backdrop-blur-md p-4 flex flex-col justify-between shadow-xl">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-1.5">
            <ShieldAlert size={14} className="text-emerald-400" /> Risk &amp; Circuit Breaker
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
            SECURE
          </span>
        </div>

        <div className="space-y-2 text-xs">
          <div className="bg-black/40 p-2.5 rounded-xl border border-white/5 flex justify-between items-center">
            <span className="text-white/60">Risk Lot Mode</span>
            <span className="font-mono font-bold text-white">Fixed 0.01 (Safe)</span>
          </div>
          <div className="bg-black/40 p-2.5 rounded-xl border border-white/5 flex justify-between items-center">
            <span className="text-white/60">Anti-Hedging Rule</span>
            <span className="font-bold text-emerald-400 flex items-center gap-1">
              <CheckCircle2 size={12} /> Active
            </span>
          </div>
          <div className="bg-black/40 p-2.5 rounded-xl border border-white/5 flex justify-between items-center">
            <span className="text-white/60">Friday Liquidator</span>
            <span className="font-mono font-semibold text-white/80">Sabtu 00:00 WIB (1x)</span>
          </div>
        </div>

        <div className="mt-2.5 pt-2 border-t border-white/5 flex items-center justify-between text-[10px] text-white/40">
          <span>Fat-Finger Cap: Max 0.10 Lot</span>
          <span>Spread Limit: Dynamic</span>
        </div>
      </div>
    </div>
  );
};
