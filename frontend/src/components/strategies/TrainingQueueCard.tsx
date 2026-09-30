"use client";

import React, { useState, useEffect } from "react";
import { 
  Layers, 
  Plus, 
  Trash2, 
  Play, 
  Square, 
  CheckCircle, 
  XCircle, 
  Clock, 
  Loader2, 
  Flame, 
  RefreshCw, 
  Sparkles,
  ArrowRight,
  ShieldCheck,
  Zap
} from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import { QueueConfirmModal, QueueTask } from "./QueueConfirmModal";

interface TrainingQueueCardProps {
  selectedPair: string;
  pairs: any[];
  onQueueComplete?: () => void;
}

export function TrainingQueueCard({ selectedPair, pairs, onQueueComplete }: TrainingQueueCardProps) {
  const toast = useToast();
  const [tasks, setTasks] = useState<QueueTask[]>([]);
  const [inputPair, setInputPair] = useState<string>(selectedPair);
  const [inputMode, setInputMode] = useState<"normal" | "runner" | "both">("both");
  const [inputType, setInputType] = useState<"full" | "incremental">("incremental");
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  // Server state
  const [serverQueue, setServerQueue] = useState<{
    is_running: boolean;
    current_task_id: string | null;
    post_completion_action: string;
    total_tasks: number;
    completed_tasks: number;
    started_at: string | null;
    completed_at: string | null;
    tasks: any[];
  }>({
    is_running: false,
    current_task_id: null,
    post_completion_action: "idle",
    total_tasks: 0,
    completed_tasks: 0,
    started_at: null,
    completed_at: null,
    tasks: []
  });

  // Sinkronkan input pair dengan selected pair dari parent jika berganti
  useEffect(() => {
    if (selectedPair) {
      setInputPair(selectedPair);
    }
  }, [selectedPair]);

  // Polling server queue status
  const fetchQueueStatus = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/queue-status`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === "success") {
          const wasRunning = serverQueue.is_running;
          setServerQueue(data);
          // Jika baru saja selesai dari running
          if (wasRunning && !data.is_running && onQueueComplete) {
            onQueueComplete();
          }
        }
      }
    } catch {
      // ignore polling errors
    }
  };

  useEffect(() => {
    fetchQueueStatus();
    const interval = setInterval(fetchQueueStatus, 2500);
    return () => clearInterval(interval);
  }, [serverQueue.is_running]);

  const addTask = (sym: string, mode: "normal" | "runner", type: "full" | "incremental") => {
    const newTask: QueueTask = {
      id: Math.random().toString(36).substring(2, 9),
      symbol: sym.toUpperCase(),
      mode,
      type
    };
    setTasks(prev => [...prev, newTask]);
  };

  const handleAddCustom = () => {
    if (inputMode === "both") {
      addTask(inputPair, "normal", inputType);
      addTask(inputPair, "runner", inputType);
      toast.info(`Menambahkan 2 tugas (${inputPair} Normal & Runner ${inputType.toUpperCase()}) ke antrean.`, "Antrean Tugas");
    } else {
      addTask(inputPair, inputMode, inputType);
      toast.info(`Menambahkan ${inputPair} ${inputMode.toUpperCase()} (${inputType.toUpperCase()}) ke antrean.`, "Antrean Tugas");
    }
  };

  const handleAddPreset = (preset: "both_full" | "both_incremental" | "all_pairs_incremental") => {
    if (preset === "both_full") {
      addTask(inputPair, "normal", "full");
      addTask(inputPair, "runner", "full");
      toast.success(`Preset diterapkan: Normal & Runner Full Retrain (${inputPair})`, "Preset Antrean");
    } else if (preset === "both_incremental") {
      addTask(inputPair, "normal", "incremental");
      addTask(inputPair, "runner", "incremental");
      toast.success(`Preset diterapkan: Normal & Runner Incremental (${inputPair})`, "Preset Antrean");
    } else if (preset === "all_pairs_incremental") {
      const pairList = pairs.length > 0 ? pairs.map(p => p.symbol) : [inputPair];
      pairList.forEach(p => {
        addTask(p, "normal", "incremental");
        addTask(p, "runner", "incremental");
      });
      toast.success(`Preset multi-pair diterapkan untuk ${pairList.length} pair.`, "Preset Antrean");
    }
  };

  const removeTask = (id: string) => {
    setTasks(prev => prev.filter(t => t.id !== id));
  };

  const clearQueue = () => {
    setTasks([]);
  };

  const handleStartQueue = async (postAction: "idle" | "force_live", autoApply: boolean) => {
    if (tasks.length === 0) return;
    setIsSubmitting(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/queue-train`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tasks,
          post_completion_action: postAction,
          auto_apply: autoApply
        })
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.success(
          data.message || "Antrean training berhasil dijalankan di background.",
          "Batch Training Diluncurkan"
        );
        setIsConfirmModalOpen(false);
        setTasks([]); // Kosongkan builder karena sudah dipindahkan ke backend queue
        fetchQueueStatus();
      } else {
        toast.error(data.message || "Gagal memulai antrean training.", "Error Antrean");
      }
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Error Koneksi");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancelQueue = async () => {
    setIsCancelling(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/queue-cancel`, {
        method: "POST"
      });
      const data = await res.json();
      toast.warning(data.message || "Antrean dibatalkan.", "Pembatalan");
      fetchQueueStatus();
    } catch {
      toast.error("Gagal membatalkan antrean di backend.", "Error");
    } finally {
      setIsCancelling(false);
    }
  };

  const availablePairSymbols = pairs.length > 0 ? pairs.map(p => p.symbol) : ["XAUUSD"];

  return (
    <div className="mb-6 p-5 rounded-2xl bg-zinc-950/70 border border-white/10 shadow-xl backdrop-blur-md">
      {/* Title Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-brand-green" />
            <h2 className="text-base font-black text-white tracking-wide uppercase">
              Batch Training Pipeline (Queue)
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-brand-green/20 text-brand-green border border-brand-green/30 font-bold">
              Automated
            </span>
          </div>
          <p className="text-xs text-white/50 mt-1">
            Susun beberapa tugas pelatihan sekaligus. Eksekusi sekuensial otomatis dengan pilihan pasca antrean (Kembali IDLE / Beralih FORCE LIVE).
          </p>
        </div>

        {/* Server Status Badge */}
        {serverQueue.is_running && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-bold animate-pulse">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>
              Sedang Melatih ({serverQueue.completed_tasks + 1}/{serverQueue.total_tasks})
            </span>
          </div>
        )}
      </div>

      {/* ACTIVE RUNNING SERVER QUEUE MONITOR */}
      {serverQueue.is_running && (
        <div className="mt-4 p-4 rounded-xl bg-amber-500/5 border border-amber-500/20">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
            <div>
              <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block">
                Antrean Berjalan di Latar Belakang
              </span>
              <span className="text-[11px] text-white/50">
                Aksi pasca selesai: <strong className="text-white uppercase">{serverQueue.post_completion_action.replace("_", " ")}</strong>
              </span>
            </div>
            <button
              onClick={handleCancelQueue}
              disabled={isCancelling}
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-brand-red bg-brand-red/10 hover:bg-brand-red/20 border border-brand-red/30 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              {isCancelling ? <Loader2 className="w-3 h-3 animate-spin" /> : <Square className="w-3 h-3" />}
              Batalkan Sisa Antrean
            </button>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-black/40 h-2 rounded-full overflow-hidden mb-3 border border-white/5">
            <div 
              className="bg-brand-green h-full transition-all duration-500 rounded-full"
              style={{
                width: `${Math.round((serverQueue.completed_tasks / (serverQueue.total_tasks || 1)) * 100)}%`
              }}
            />
          </div>

          {/* Tasks in Server Queue */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {serverQueue.tasks.map((st, i) => {
              const isCurrent = st.id === serverQueue.current_task_id;
              return (
                <div 
                  key={st.id || i}
                  className={`p-2.5 rounded-lg border text-xs flex items-center justify-between ${
                    st.status === "completed"
                      ? "bg-brand-green/5 border-brand-green/20 text-white/80"
                      : st.status === "running"
                      ? "bg-amber-500/10 border-amber-500/40 text-amber-300 ring-1 ring-amber-500/30"
                      : st.status === "failed"
                      ? "bg-red-500/10 border-red-500/30 text-red-300"
                      : "bg-white/[0.02] border-white/5 text-white/40"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {st.status === "completed" && <CheckCircle className="w-3.5 h-3.5 text-brand-green shrink-0" />}
                    {st.status === "running" && <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin shrink-0" />}
                    {st.status === "failed" && <XCircle className="w-3.5 h-3.5 text-brand-red shrink-0" />}
                    {st.status === "pending" && <Clock className="w-3.5 h-3.5 text-white/30 shrink-0" />}
                    <div>
                      <span className="font-bold">{st.symbol} {st.mode?.toUpperCase()}</span>
                      <span className="text-[10px] opacity-60 ml-1.5">({st.type})</span>
                    </div>
                  </div>
                  <span className="text-[10px] font-semibold">
                    {st.status === "completed" && st.accuracy ? `${(st.accuracy * 100).toFixed(1)}%` : st.status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* QUICK PRESETS */}
      <div className="mt-4">
        <label className="text-[11px] font-bold text-white/40 uppercase tracking-wider block mb-2">
          Preset Cepat ({inputPair}):
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => handleAddPreset("both_incremental")}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <RefreshCw className="w-3 h-3" />
            + Both Incremental ({inputPair})
          </button>
          <button
            onClick={() => handleAddPreset("both_full")}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <Flame className="w-3 h-3" />
            + Both Full Retrain ({inputPair})
          </button>
          {pairs.length > 1 && (
            <button
              onClick={() => handleAddPreset("all_pairs_incremental")}
              className="px-3 py-1.5 rounded-xl text-xs font-semibold text-purple-400 bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/20 transition-all flex items-center gap-1.5 cursor-pointer"
            >
              <Sparkles className="w-3 h-3" />
              + All Registered Pairs (Incremental)
            </button>
          )}
        </div>
      </div>

      {/* TASK BUILDER FORM */}
      <div className="mt-4 p-3.5 rounded-xl bg-white/[0.02] border border-white/5 flex flex-wrap items-center gap-3">
        {/* Pair Selector */}
        <div className="flex flex-col gap-1 min-w-[120px]">
          <span className="text-[10px] font-bold text-white/50 uppercase">Pair</span>
          <select
            value={inputPair}
            onChange={(e) => setInputPair(e.target.value)}
            className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs font-bold text-white focus:outline-none focus:border-brand-green"
          >
            {availablePairSymbols.map((s) => (
              <option key={s} value={s} className="bg-zinc-900 text-white">
                {s}
              </option>
            ))}
          </select>
        </div>

        {/* Mode Selector */}
        <div className="flex flex-col gap-1 min-w-[140px]">
          <span className="text-[10px] font-bold text-white/50 uppercase">Mode AI</span>
          <select
            value={inputMode}
            onChange={(e) => setInputMode(e.target.value as any)}
            className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs font-bold text-white focus:outline-none focus:border-brand-green"
          >
            <option value="both" className="bg-zinc-900 text-white">Both (Normal &amp; Runner)</option>
            <option value="normal" className="bg-zinc-900 text-white">Normal (Scalp 1:2)</option>
            <option value="runner" className="bg-zinc-900 text-white">Runner (Trend 1:5)</option>
          </select>
        </div>

        {/* Type Selector */}
        <div className="flex flex-col gap-1 min-w-[140px]">
          <span className="text-[10px] font-bold text-white/50 uppercase">Tipe Latihan</span>
          <select
            value={inputType}
            onChange={(e) => setInputType(e.target.value as any)}
            className="bg-black/40 border border-white/10 rounded-lg px-2.5 py-1.5 text-xs font-bold text-white focus:outline-none focus:border-brand-green"
          >
            <option value="incremental" className="bg-zinc-900 text-white">Incremental Retrain</option>
            <option value="full" className="bg-zinc-900 text-white">Full Retrain (Optuna)</option>
          </select>
        </div>

        {/* Add Button */}
        <button
          onClick={handleAddCustom}
          className="self-end px-4 py-2 rounded-lg text-xs font-bold text-white bg-white/10 hover:bg-white/20 border border-white/15 transition-all flex items-center gap-1.5 cursor-pointer ml-auto"
        >
          <Plus className="w-3.5 h-3.5" />
          Tambah ke Antrean
        </button>
      </div>

      {/* PENDING QUEUE LIST (READY TO EXECUTE) */}
      <div className="mt-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-bold text-white/70 uppercase tracking-wider flex items-center gap-1.5">
            Daftar Antrean Tugas Baru ({tasks.length})
          </span>
          {tasks.length > 0 && (
            <button
              onClick={clearQueue}
              className="text-[11px] font-semibold text-brand-red/80 hover:text-brand-red transition-colors flex items-center gap-1 cursor-pointer"
            >
              <Trash2 className="w-3 h-3" /> Kosongkan
            </button>
          )}
        </div>

        {tasks.length === 0 ? (
          <div className="p-4 rounded-xl border border-dashed border-white/10 text-center text-xs text-white/40">
            Belum ada tugas latihan di antrean. Gunakan preset cepat di atas atau tambahkan tugas kustom untuk dieksekusi secara batch.
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((task, idx) => (
              <div
                key={task.id}
                className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.03] border border-white/5 hover:border-white/10 transition-all text-xs"
              >
                <div className="flex items-center gap-2.5">
                  <span className="w-5 h-5 rounded-md bg-white/10 text-white/60 font-mono text-[10px] flex items-center justify-center font-bold">
                    #{idx + 1}
                  </span>
                  <span className="font-bold text-white">{task.symbol}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    task.mode === "normal"
                      ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                      : "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                  }`}>
                    {task.mode.toUpperCase()}
                  </span>
                  <span className={`flex items-center gap-1 text-[11px] font-medium ${
                    task.type === "full" ? "text-amber-400" : "text-emerald-400"
                  }`}>
                    {task.type === "full" ? <Flame className="w-3 h-3" /> : <RefreshCw className="w-3 h-3" />}
                    {task.type.toUpperCase()}
                  </span>
                </div>
                <button
                  onClick={() => removeTask(task.id)}
                  className="p-1 rounded-md text-white/40 hover:text-brand-red hover:bg-brand-red/10 transition-colors cursor-pointer"
                  title="Hapus tugas ini"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}

            {/* Execute Button */}
            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setIsConfirmModalOpen(true)}
                disabled={serverQueue.is_running || tasks.length === 0}
                className="px-6 py-2.5 rounded-xl text-xs font-black text-black bg-brand-green hover:bg-brand-green/90 transition-all flex items-center gap-2 shadow-lg shadow-brand-green/20 disabled:opacity-50 cursor-pointer"
              >
                <Play className="w-4 h-4 fill-current" />
                Jalankan Antrean ({tasks.length} Tugas)
              </button>
            </div>
          </div>
        )}
      </div>

      {/* CONFIRMATION MODAL WITH IDLE vs FORCE LIVE SELECTION */}
      <QueueConfirmModal
        isOpen={isConfirmModalOpen}
        tasks={tasks}
        isLoading={isSubmitting}
        onClose={() => setIsConfirmModalOpen(false)}
        onConfirm={handleStartQueue}
      />
    </div>
  );
}
