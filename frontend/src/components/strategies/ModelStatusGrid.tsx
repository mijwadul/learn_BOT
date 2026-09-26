"use client";

import React from "react";
import { BrainCircuit, Loader2, Zap, ShieldAlert, Power, CheckCircle2, XCircle } from "lucide-react";

interface ModelInfo {
  trained: boolean;
  status: string;
  is_training: boolean;
  last_accuracy: number;
  is_active?: boolean;
}

interface ModelStatusGridProps {
  modelsStatus: {
    normal: ModelInfo;
    runner: ModelInfo;
  };
  loading: boolean;
  onTrain: (mode: string, type: "incremental" | "full") => void;
  onForceMode: (mode: string, action: "force_live" | "quarantine") => void;
  onToggleBrain?: (mode: "normal" | "runner" | "all", active: boolean) => void;
}

export function ModelStatusGrid({
  modelsStatus,
  loading,
  onTrain,
  onForceMode,
  onToggleBrain,
}: ModelStatusGridProps) {
  const isNormalActive = modelsStatus.normal.is_active ?? modelsStatus.normal.status.includes("LIVE");
  const isRunnerActive = modelsStatus.runner.is_active ?? modelsStatus.runner.status.includes("LIVE");
  const isAllActive = isNormalActive && isRunnerActive;
  const isNoneActive = !isNormalActive && !isRunnerActive;

  return (
    <div className="flex flex-col gap-4 mb-6 md:mb-8 shrink-0">
      {/* Master Otak Activation Bar */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-4 sm:p-5 shadow-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm sm:text-base font-bold text-white flex items-center gap-2">
              <Power className="text-brand-green w-4 h-4 sm:w-5 sm:h-5" />
              Master Saklar Otak AI
            </span>
            <span
              className={`px-2.5 py-0.5 rounded-full text-[10px] sm:text-xs font-bold border ${
                isAllActive
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                  : isNoneActive
                  ? "bg-rose-500/20 text-rose-400 border-rose-500/40"
                  : "bg-amber-500/20 text-amber-300 border-amber-500/40"
              }`}
            >
              {isAllActive ? "SEMUA OTAK AKTIF" : isNoneActive ? "SEMUA OTAK NONAKTIF" : "SEBAGIAN AKTIF"}
            </span>
          </div>
          <p className="text-xs text-white/50 mt-1">
            Nyalakan atau matikan salah satu atau kedua otak (Scalp 1:2 &amp; Trend Runner 1:5) secara instan.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              if (onToggleBrain) onToggleBrain("all", true);
              else onForceMode("all", "force_live");
            }}
            className="flex-1 sm:flex-initial px-4 py-2.5 rounded-xl font-black text-xs bg-emerald-500 hover:bg-emerald-400 text-black shadow-lg shadow-emerald-500/20 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <Zap size={14} className="fill-black" />
            <span>Aktifkan Semua Otak</span>
          </button>

          <button
            type="button"
            disabled={loading}
            onClick={() => {
              if (onToggleBrain) onToggleBrain("all", false);
              else onForceMode("all", "quarantine");
            }}
            className="flex-1 sm:flex-initial px-4 py-2.5 rounded-xl font-bold text-xs bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <ShieldAlert size={14} />
            <span>Matikan Semua Otak</span>
          </button>
        </div>
      </div>

      {/* Grid Otak Individual */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        {/* Normal Mode (Scalp 1:2) */}
        <div
          className={`bg-[#0b1210] border rounded-2xl p-5 shadow-xl flex flex-col justify-between transition-all ${
            isNormalActive ? "border-brand-green/40 shadow-brand-green/5" : "border-white/10"
          }`}
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${isNormalActive ? "bg-emerald-400 animate-pulse" : "bg-white/30"}`} />
                <h2 className="text-base sm:text-lg font-bold text-white">Otak Scalping (Normal 1:2)</h2>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-bold">
                <span
                  className={`px-2.5 py-0.5 rounded-full ${
                    modelsStatus.normal.trained
                      ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                      : "bg-white/10 text-white/50"
                  }`}
                >
                  {modelsStatus.normal.trained ? "TRAINED" : "UNTRAINED"}
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded-full font-bold ${
                    isNormalActive
                      ? "bg-brand-green/20 text-brand-green border border-brand-green/30"
                      : "bg-brand-red/20 text-brand-red border border-brand-red/30"
                  }`}
                >
                  {isNormalActive ? "LIVE / AKTIF" : "IDLE / OFF"}
                </span>
              </div>
            </div>

            <p className="text-xs sm:text-sm text-white/50 mb-3">
              Intraday scalping BBMA Re-entry berpedoman pada RR pas 1:2 dengan pelindung BE pada 1R.
            </p>

            {/* Quick Toggle Switch for Normal Brain */}
            <div className="my-3 p-3 rounded-xl bg-black/40 border border-white/5 flex items-center justify-between">
              <div>
                <span className="text-xs font-bold text-white block">Status Eksekusi Live</span>
                <span className="text-[11px] text-white/40">
                  {isNormalActive ? "Otak ini sedang mengeksekusi order scalp" : "Otak sedang diistirahatkan (Quarantine)"}
                </span>
              </div>

              <button
                type="button"
                disabled={loading}
                onClick={() => {
                  if (onToggleBrain) onToggleBrain("normal", !isNormalActive);
                  else onForceMode("normal", isNormalActive ? "quarantine" : "force_live");
                }}
                className={`px-3.5 py-1.5 rounded-xl font-black text-xs flex items-center gap-2 transition-all cursor-pointer ${
                  isNormalActive
                    ? "bg-brand-green text-black shadow-lg shadow-brand-green/30 font-extrabold"
                    : "bg-white/10 hover:bg-white/20 text-white/70 border border-white/10"
                }`}
              >
                {isNormalActive ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                <span>{isNormalActive ? "AKTIF (KLIK UNTUK OFF)" : "NONAKTIF (KLIK UNTUK AKTIF)"}</span>
              </button>
            </div>

            {modelsStatus.normal.trained && (
              <div className="mb-4 inline-block">
                <span
                  className={`px-3 py-1 rounded-xl text-xs font-bold border ${
                    modelsStatus.normal.last_accuracy >= 0.50
                      ? "bg-brand-green/10 text-brand-green border-brand-green/30"
                      : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  }`}
                >
                  OOS Validation Score: {(modelsStatus.normal.last_accuracy * 100).toFixed(1)}%
                </span>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2.5 pt-2 border-t border-white/5">
            <span className="text-[11px] uppercase tracking-wider text-white/40 font-semibold">Pelatihan AI &amp; Override</span>
            <div className="grid grid-cols-2 gap-2.5">
              <button
                disabled={loading || modelsStatus.normal.is_training}
                onClick={() => onTrain("normal", "incremental")}
                className="bg-brand-blue/20 hover:bg-brand-blue/30 text-brand-blue border border-brand-blue/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs disabled:opacity-50 cursor-pointer"
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
                className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs disabled:opacity-50 cursor-pointer"
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
                className="bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/40 p-2 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs cursor-pointer"
              >
                <Zap size={14} /> Force LIVE
              </button>
              <button
                disabled={loading}
                onClick={() => onForceMode("normal", "quarantine")}
                className="bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/40 p-2 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs cursor-pointer"
              >
                <ShieldAlert size={14} /> Quarantine
              </button>
            </div>
          </div>
        </div>

        {/* Runner Mode (Trend 1:5) */}
        <div
          className={`bg-[#0b1210] border rounded-2xl p-5 shadow-xl flex flex-col justify-between transition-all ${
            isRunnerActive ? "border-purple-500/40 shadow-purple-500/5" : "border-white/10"
          }`}
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${isRunnerActive ? "bg-purple-400 animate-pulse" : "bg-white/30"}`} />
                <h2 className="text-base sm:text-lg font-bold text-white">Otak Trend Runner (Mode 1:5)</h2>
              </div>
              <div className="flex items-center gap-1.5 text-xs font-bold">
                <span
                  className={`px-2.5 py-0.5 rounded-full ${
                    modelsStatus.runner.trained
                      ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                      : "bg-white/10 text-white/50"
                  }`}
                >
                  {modelsStatus.runner.trained ? "TRAINED" : "UNTRAINED"}
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded-full font-bold ${
                    isRunnerActive
                      ? "bg-brand-green/20 text-brand-green border border-brand-green/30"
                      : "bg-brand-red/20 text-brand-red border border-brand-red/30"
                  }`}
                >
                  {isRunnerActive ? "LIVE / AKTIF" : "IDLE / OFF"}
                </span>
              </div>
            </div>

            <p className="text-xs sm:text-sm text-white/50 mb-3">
              Trend-following dinamis dengan milestone partial close 50% di 2R dan target hingga 5R.
            </p>

            {/* Quick Toggle Switch for Runner Brain */}
            <div className="my-3 p-3 rounded-xl bg-black/40 border border-white/5 flex items-center justify-between">
              <div>
                <span className="text-xs font-bold text-white block">Status Eksekusi Live</span>
                <span className="text-[11px] text-white/40">
                  {isRunnerActive ? "Otak ini sedang mengeksekusi order trend runner" : "Otak sedang diistirahatkan (Quarantine)"}
                </span>
              </div>

              <button
                type="button"
                disabled={loading}
                onClick={() => {
                  if (onToggleBrain) onToggleBrain("runner", !isRunnerActive);
                  else onForceMode("runner", isRunnerActive ? "quarantine" : "force_live");
                }}
                className={`px-3.5 py-1.5 rounded-xl font-black text-xs flex items-center gap-2 transition-all cursor-pointer ${
                  isRunnerActive
                    ? "bg-purple-500 text-white shadow-lg shadow-purple-500/30 font-extrabold"
                    : "bg-white/10 hover:bg-white/20 text-white/70 border border-white/10"
                }`}
              >
                {isRunnerActive ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
                <span>{isRunnerActive ? "AKTIF (KLIK UNTUK OFF)" : "NONAKTIF (KLIK UNTUK AKTIF)"}</span>
              </button>
            </div>

            {modelsStatus.runner.trained && (
              <div className="mb-4 inline-block">
                <span
                  className={`px-3 py-1 rounded-xl text-xs font-bold border ${
                    modelsStatus.runner.last_accuracy >= 0.50
                      ? "bg-brand-green/10 text-brand-green border-brand-green/30"
                      : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                  }`}
                >
                  OOS Validation Score: {(modelsStatus.runner.last_accuracy * 100).toFixed(1)}%
                </span>
              </div>
            )}
          </div>

          <div className="flex flex-col gap-2.5 pt-2 border-t border-white/5">
            <span className="text-[11px] uppercase tracking-wider text-white/40 font-semibold">Pelatihan AI &amp; Override</span>
            <div className="grid grid-cols-2 gap-2.5">
              <button
                disabled={loading || modelsStatus.runner.is_training}
                onClick={() => onTrain("runner", "incremental")}
                className="bg-brand-blue/20 hover:bg-brand-blue/30 text-brand-blue border border-brand-blue/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs disabled:opacity-50 cursor-pointer"
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
                className="bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/40 p-2.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs disabled:opacity-50 cursor-pointer"
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
                className="bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/40 p-2 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs cursor-pointer"
              >
                <Zap size={14} /> Force LIVE
              </button>
              <button
                disabled={loading}
                onClick={() => onForceMode("runner", "quarantine")}
                className="bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/40 p-2 rounded-xl font-bold flex items-center justify-center gap-1.5 transition-all text-xs cursor-pointer"
              >
                <ShieldAlert size={14} /> Quarantine
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
