"use client";

import React from "react";
import { Brain, CheckCircle2, AlertTriangle, X, Save, Trash2, ArrowUpRight, ArrowDownRight, Layers, Target, ShieldCheck, Activity } from "lucide-react";

export interface PendingModelInfo {
  symbol: string;
  mode: string;
  train_type: string;
  calibrated_threshold: number;
  features?: string[];
  passed_oos: boolean;
  new_accuracy: number;
  old_accuracy: number;
  profit_factor: number;
  expectancy: number;
  max_drawdown: number;
  total_trades: number;
  reasons?: string[];
  trained_at: string;
}

interface ConfirmSaveModelModalProps {
  isOpen: boolean;
  data: PendingModelInfo | null;
  isLoading: boolean;
  onSave: () => void | Promise<void>;
  onDiscard: () => void | Promise<void>;
  onClose: () => void;
}

export function ConfirmSaveModelModal({
  isOpen,
  data,
  isLoading,
  onSave,
  onDiscard,
  onClose,
}: ConfirmSaveModelModalProps) {
  if (!isOpen || !data) return null;

  const modeUpper = (data.mode || "normal").toUpperCase();
  const trainTypeUpper = (data.train_type || "incremental").toUpperCase();
  const isPassed = data.passed_oos;
  const accDiff = (data.new_accuracy - data.old_accuracy) * 100;

  return (
    <div className="fixed inset-0 z-[160] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/85 backdrop-blur-md transition-opacity animate-in fade-in"
        onClick={isLoading ? undefined : onClose}
      />

      {/* Modal Card */}
      <div className="relative w-full max-w-xl bg-[#0c1412] border border-white/15 rounded-3xl p-6 sm:p-7 shadow-2xl z-10 animate-in zoom-in-95 duration-200 flex flex-col gap-5 max-h-[90vh] overflow-y-auto">
        
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-white/10 pb-4">
          <div className="flex items-center gap-3.5">
            <div className={`p-3 rounded-2xl border ${
              isPassed 
                ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400" 
                : "bg-amber-500/15 border-amber-500/30 text-amber-400"
            }`}>
              <Brain className="w-6 h-6 sm:w-7 sm:h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg sm:text-xl font-black text-white tracking-tight">
                  Simpan Checkpoint Model AI?
                </h3>
                <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider border ${
                  isPassed
                    ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                    : "bg-amber-500/20 text-amber-400 border-amber-500/40"
                }`}>
                  {isPassed ? "Lolos Gate OOS" : "Perlu Evaluasi"}
                </span>
              </div>
              <p className="text-xs sm:text-sm text-white/60 mt-0.5">
                Pair: <span className="font-bold text-white">{data.symbol}</span> • Mode: <span className="font-bold text-brand-green">{modeUpper}</span> • Pelatihan: <span className="font-bold text-purple-300">{trainTypeUpper}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="text-white/40 hover:text-white p-1 rounded-xl transition-colors shrink-0 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scorecard Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {/* Win Rate */}
          <div className="bg-black/40 border border-white/10 rounded-2xl p-3 flex flex-col justify-between">
            <span className="text-[11px] font-medium text-white/50 flex items-center gap-1">
              <Activity size={12} className="text-brand-green" /> Win Rate OOS
            </span>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="text-lg font-black text-white">
                {(data.new_accuracy * 100).toFixed(1)}%
              </span>
              {data.old_accuracy > 0 && (
                <span className={`text-[10px] font-bold flex items-center ${accDiff >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {accDiff >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                  {accDiff >= 0 ? `+${accDiff.toFixed(1)}%` : `${accDiff.toFixed(1)}%`}
                </span>
              )}
            </div>
            <span className="text-[10px] text-white/40 mt-0.5">
              Lama: {(data.old_accuracy * 100).toFixed(1)}%
            </span>
          </div>

          {/* Profit Factor */}
          <div className="bg-black/40 border border-white/10 rounded-2xl p-3 flex flex-col justify-between">
            <span className="text-[11px] font-medium text-white/50 flex items-center gap-1">
              <Target size={12} className="text-cyan-400" /> Profit Factor
            </span>
            <div className="mt-1">
              <span className={`text-lg font-black ${data.profit_factor >= 1.5 ? "text-emerald-400" : "text-amber-400"}`}>
                {data.profit_factor.toFixed(2)}x
              </span>
            </div>
            <span className="text-[10px] text-white/40 mt-0.5">
              Target: &ge; 1.50x
            </span>
          </div>

          {/* Expectancy */}
          <div className="bg-black/40 border border-white/10 rounded-2xl p-3 flex flex-col justify-between">
            <span className="text-[11px] font-medium text-white/50 flex items-center gap-1">
              <ShieldCheck size={12} className="text-purple-400" /> Expectancy
            </span>
            <div className="mt-1">
              <span className={`text-lg font-black ${data.expectancy >= 0.25 ? "text-emerald-400" : "text-white"}`}>
                {data.expectancy >= 0 ? `+${data.expectancy.toFixed(2)}R` : `${data.expectancy.toFixed(2)}R`}
              </span>
            </div>
            <span className="text-[10px] text-white/40 mt-0.5">
              Target: &ge; +0.25R
            </span>
          </div>

          {/* Max Drawdown */}
          <div className="bg-black/40 border border-white/10 rounded-2xl p-3 flex flex-col justify-between">
            <span className="text-[11px] font-medium text-white/50">Max Drawdown</span>
            <div className="mt-1">
              <span className={`text-base font-bold ${data.max_drawdown <= 6.0 ? "text-emerald-400" : "text-rose-400"}`}>
                {data.max_drawdown.toFixed(1)}%
              </span>
            </div>
            <span className="text-[10px] text-white/40 mt-0.5">
              Limit: &le; 6.0%
            </span>
          </div>

          {/* Calibrated Threshold */}
          <div className="bg-black/40 border border-white/10 rounded-2xl p-3 flex flex-col justify-between">
            <span className="text-[11px] font-medium text-white/50">Threshold Sinyal</span>
            <div className="mt-1">
              <span className="text-base font-bold text-white">
                {(data.calibrated_threshold * 100).toFixed(1)}%
              </span>
            </div>
            <span className="text-[10px] text-white/40 mt-0.5">
              Optimal Threshold
            </span>
          </div>

          {/* Total Trades OOS */}
          <div className="bg-black/40 border border-white/10 rounded-2xl p-3 flex flex-col justify-between">
            <span className="text-[11px] font-medium text-white/50 flex items-center gap-1">
              <Layers size={12} className="text-amber-400" /> Sampel Trades
            </span>
            <div className="mt-1">
              <span className="text-base font-bold text-white">
                {data.total_trades} trades
              </span>
            </div>
            <span className="text-[10px] text-white/40 mt-0.5">
              Simulasi OOS
            </span>
          </div>
        </div>

        {/* Reasons / Evaluation notes */}
        {data.reasons && data.reasons.length > 0 && (
          <div className={`p-3.5 rounded-2xl border text-xs leading-relaxed ${
            isPassed 
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-300"
              : "bg-amber-500/10 border-amber-500/20 text-amber-300"
          }`}>
            <span className="font-bold flex items-center gap-1.5 mb-1">
              {isPassed ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
              Catatan Evaluasi Fit &amp; Proper Test:
            </span>
            <ul className="list-disc list-inside space-y-0.5 pl-1 text-[11px] text-white/80">
              {data.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Confirmation Notice */}
        <div className="p-3.5 rounded-2xl bg-white/5 border border-white/10 text-xs text-white/70 leading-relaxed">
          <p>
            <span className="font-bold text-white">Pemberitahuan Penyimpanan:</span> Jika Anda menekan <span className="text-brand-green font-bold">Simpan &amp; Timpa</span>, file model <code className="text-amber-300 font-mono">model_{data.mode}.pkl</code> yang lama di subdirektori <code className="text-amber-300 font-mono">models/{data.symbol}/</code> akan langsung <span className="text-white font-bold underline">ditimpa</span> dengan model baru ini. Jika Anda memilih <span className="text-rose-400 font-bold">Tolak / Buang</span>, model baru ini akan dihapus dan model lama tetap aktif.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onDiscard}
            disabled={isLoading}
            className="w-full sm:w-auto px-4 py-2.5 rounded-xl border border-rose-500/30 hover:border-rose-500/50 bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 font-bold text-xs transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <Trash2 size={14} />
            <span>Tolak &amp; Buang Model Ini</span>
          </button>

          <button
            type="button"
            onClick={onSave}
            disabled={isLoading}
            className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-brand-green hover:bg-brand-green/90 text-black font-black text-xs shadow-lg shadow-brand-green/30 transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {isLoading ? (
              <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
            ) : (
              <Save size={15} />
            )}
            <span>Simpan &amp; Timpa Model (.pkl)</span>
          </button>
        </div>

      </div>
    </div>
  );
}
