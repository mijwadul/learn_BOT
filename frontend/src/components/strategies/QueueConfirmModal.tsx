"use client";

import React, { useState } from "react";
import { 
  PlayCircle, 
  PauseCircle, 
  X, 
  CheckCircle2, 
  Layers, 
  Flame, 
  RefreshCw, 
  AlertTriangle,
  Loader2
} from "lucide-react";

export interface QueueTask {
  id: string;
  symbol: string;
  mode: "normal" | "runner";
  type: "full" | "incremental";
}

interface QueueConfirmModalProps {
  isOpen: boolean;
  tasks: QueueTask[];
  isLoading: boolean;
  onClose: () => void;
  onConfirm: (postAction: "idle" | "force_live", autoApply: boolean) => void;
}

export function QueueConfirmModal({
  isOpen,
  tasks,
  isLoading,
  onClose,
  onConfirm,
}: QueueConfirmModalProps) {
  const [postAction, setPostAction] = useState<"idle" | "force_live">("idle");
  const [autoApply, setAutoApply] = useState<boolean>(true);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="w-full max-w-xl rounded-2xl bg-zinc-950 border border-white/10 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-white/10 flex items-center justify-between bg-zinc-900/60">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-brand-green/10 border border-brand-green/30 flex items-center justify-center text-brand-green">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-white tracking-wide">
                Konfirmasi Antrean Pelatihan AI
              </h2>
              <p className="text-xs text-white/50">
                Verifikasi daftar tugas dan tentukan status sistem pasca antrean
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="p-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/5 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto space-y-5 scrollbar-thin">
          {/* Ringkasan Tugas */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-white/70 uppercase tracking-wider">
                Daftar Tugas Eksekusi ({tasks.length})
              </span>
              <span className="text-[11px] text-white/40">Urutan Eksekusi: FIFO</span>
            </div>
            <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
              {tasks.map((task, idx) => (
                <div 
                  key={task.id || idx}
                  className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.03] border border-white/5 text-xs"
                >
                  <div className="flex items-center gap-2.5">
                    <span className="w-5 h-5 rounded-md bg-white/10 text-white/70 font-mono text-[10px] flex items-center justify-center font-bold">
                      #{idx + 1}
                    </span>
                    <span className="font-bold text-white">{task.symbol}</span>
                    <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${
                      task.mode === "normal"
                        ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                        : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                    }`}>
                      {task.mode.toUpperCase()}
                    </span>
                  </div>
                  <span className={`flex items-center gap-1 text-[11px] font-medium ${
                    task.type === "full" ? "text-amber-400" : "text-emerald-400"
                  }`}>
                    {task.type === "full" ? (
                      <>
                        <Flame className="w-3 h-3" /> Full Retrain (Optuna)
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-3 h-3" /> Incremental Retrain
                      </>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Pilihan Pasca Antrean (IDLE vs FORCE LIVE) */}
          <div>
            <label className="block text-xs font-bold text-white/70 uppercase tracking-wider mb-2">
              Aksi Sistem Setelah Seluruh Antrean Selesai:
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Option 1: IDLE */}
              <div
                onClick={() => setPostAction("idle")}
                className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                  postAction === "idle"
                    ? "bg-amber-500/10 border-amber-500/50 shadow-lg shadow-amber-500/10"
                    : "bg-white/[0.02] border-white/10 hover:bg-white/[0.05]"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <PauseCircle className={`w-4 h-4 ${postAction === "idle" ? "text-amber-400" : "text-white/40"}`} />
                    <span className="text-xs font-bold text-white">Kembali ke IDLE</span>
                  </div>
                  <input
                    type="radio"
                    name="postAction"
                    value="idle"
                    checked={postAction === "idle"}
                    onChange={() => setPostAction("idle")}
                    className="accent-amber-400"
                  />
                </div>
                <p className="text-[11px] text-white/50 leading-relaxed">
                  Sistem tetap standby (tidak live). Anda dapat mereview metrik model terlebih dahulu sebelum trading.
                </p>
              </div>

              {/* Option 2: FORCE LIVE */}
              <div
                onClick={() => setPostAction("force_live")}
                className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                  postAction === "force_live"
                    ? "bg-brand-green/10 border-brand-green/50 shadow-lg shadow-brand-green/10"
                    : "bg-white/[0.02] border-white/10 hover:bg-white/[0.05]"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <PlayCircle className={`w-4 h-4 ${postAction === "force_live" ? "text-brand-green" : "text-white/40"}`} />
                    <span className="text-xs font-bold text-white">Beralih ke FORCE LIVE</span>
                  </div>
                  <input
                    type="radio"
                    name="postAction"
                    value="force_live"
                    checked={postAction === "force_live"}
                    onChange={() => setPostAction("force_live")}
                    className="accent-brand-green"
                  />
                </div>
                <p className="text-[11px] text-white/50 leading-relaxed">
                  Sistem langsung mengaktifkan LIVE trading otomatis menggunakan checkpoint model baru yang selesai dilatih.
                </p>
              </div>
            </div>
          </div>

          {/* Option: Auto-Apply Checkpoint */}
          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/5 flex items-center justify-between">
            <div className="pr-3">
              <span className="text-xs font-semibold text-white block">
                Otomatis Terapkan Model (Auto-Apply)
              </span>
              <span className="text-[11px] text-white/40 block">
                Secara instan menyimpan dan menerapkan file checkpoint model baru yang lulus OOS test ke disk.
              </span>
            </div>
            <input
              type="checkbox"
              checked={autoApply}
              onChange={(e) => setAutoApply(e.target.checked)}
              className="w-4 h-4 rounded bg-zinc-800 border-white/20 text-brand-green focus:ring-brand-green accent-brand-green cursor-pointer"
            />
          </div>

          {/* Warning banner */}
          <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-start gap-2.5 text-xs text-amber-300">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
            <div>
              <p className="font-semibold">Resource CPU &amp; Waktu Eksekusi</p>
              <p className="text-[11px] text-amber-300/80 mt-0.5">
                Proses pelatihan batch akan berjalan di latar belakang secara berurutan. Anda dapat memantau log langsung di terminal atau indikator antrean.
              </p>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="p-5 border-t border-white/10 flex items-center justify-end gap-3 bg-zinc-900/60">
          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2.5 rounded-xl text-xs font-bold text-white/70 hover:text-white bg-white/5 hover:bg-white/10 transition-colors disabled:opacity-50 cursor-pointer"
          >
            Batal
          </button>
          <button
            onClick={() => onConfirm(postAction, autoApply)}
            disabled={isLoading || tasks.length === 0}
            className="px-5 py-2.5 rounded-xl text-xs font-bold text-black bg-brand-green hover:bg-brand-green/90 transition-all flex items-center gap-2 shadow-lg shadow-brand-green/20 disabled:opacity-50 cursor-pointer"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Memulai Antrean...
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4" />
                Jalankan Antrean ({tasks.length} Tugas)
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
