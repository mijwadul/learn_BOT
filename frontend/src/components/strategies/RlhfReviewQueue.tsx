"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { 
  ThumbsUp, 
  ThumbsDown, 
  MinusCircle, 
  ChevronLeft, 
  SkipForward, 
  Loader2 
} from "lucide-react";
import dynamic from "next/dynamic";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";

const SetupReviewChart = dynamic(() => import("@/components/SetupReviewChart"), { ssr: false });

export interface Setup {
  setup_id: string;
  symbol: string;
  action: "BUY" | "SELL";
  price: number;
  probability: number;
  time: string;
  sl: number;
  tp: number;
  outcome: "TP_HIT" | "SL_HIT" | "UNKNOWN";
  candles: { time: number; open: number; high: number; low: number; close: number }[];
  entry_time: number;
  tf_label: string;
  mode?: string;
  tp_multiplier?: number;
}

export function RlhfReviewQueue() {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [reviewMode, setReviewMode] = useState<"normal" | "runner">("normal");
  const [currentSetup, setCurrentSetup] = useState<Setup | null>(null);
  const [totalPending, setTotalPending] = useState(0);
  const [currentOffset, setCurrentOffset] = useState(0);
  const [minProb, setMinProb] = useState(0.65);
  const [queueLoaded, setQueueLoaded] = useState(false);
  const [queueDone, setQueueDone] = useState(false);
  const [rlhfNotes, setRlhfNotes] = useState("");
  const notesRef = useRef<HTMLInputElement>(null);

  const fetchSetup = useCallback(async (offset: number, prob: number, mode: "normal" | "runner") => {
    setLoading(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/rlhf/setups?min_prob=${prob}&offset=${offset}&mode=${mode}`);
      const data = await res.json();
      if (data.status === "done" || !data.setup) {
        setCurrentSetup(null);
        setTotalPending(data.total ?? 0);
        setQueueDone(true);
        toast.info(data.message ?? "Antrian kurasi selesai.", "RLHF Queue");
      } else {
        setCurrentSetup(data.setup);
        setTotalPending(data.total);
        setQueueDone(false);
      }
      setQueueLoaded(true);
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Error");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  const submitDecision = useCallback(async (decision: "approve" | "reject" | "ignore") => {
    if (!currentSetup || loading) return;
    setLoading(true);
    try {
      await fetch(`${getApiBaseUrl()}/api/rlhf/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          setup_id: currentSetup.setup_id,
          symbol: currentSetup.symbol,
          action_type: currentSetup.action,
          probability: currentSetup.probability,
          decision,
          notes: rlhfNotes,
          mode: reviewMode,
        }),
      });

      if (decision === "approve") {
        toast.success(`Setup ${currentSetup.setup_id} disetujui [RLHF Approved].`, "Approved");
      } else if (decision === "reject") {
        toast.warning(`Setup ${currentSetup.setup_id} ditolak [RLHF Rejected].`, "Rejected");
      } else {
        toast.info(`Setup ${currentSetup.setup_id} diabaikan (Noise).`, "Ignored");
      }

      setRlhfNotes("");
      const next = currentOffset + 1;
      setCurrentOffset(next);
      fetchSetup(next, minProb, reviewMode);
    } catch {
      toast.error("Gagal menyimpan keputusan feedback.", "Error");
      setLoading(false);
    }
  }, [currentSetup, loading, rlhfNotes, currentOffset, minProb, reviewMode, fetchSetup, toast]);

  const skipTo = useCallback((delta: number) => {
    if (loading) return;
    const next = Math.max(0, Math.min(currentOffset + delta, totalPending - 1));
    setCurrentOffset(next);
    fetchSetup(next, minProb, reviewMode);
  }, [loading, currentOffset, totalPending, minProb, reviewMode, fetchSetup]);

  // Keyboard shortcuts: A / R / I / ArrowLeft / ArrowRight
  useEffect(() => {
    if (!queueLoaded) return;
    const handler = (e: KeyboardEvent) => {
      if (document.activeElement === notesRef.current) return;
      if (e.key === "a" || e.key === "A") submitDecision("approve");
      else if (e.key === "r" || e.key === "R") submitDecision("reject");
      else if (e.key === "i" || e.key === "I") submitDecision("ignore");
      else if (e.key === "ArrowRight") skipTo(1);
      else if (e.key === "ArrowLeft") skipTo(-1);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [queueLoaded, submitDecision, skipTo]);

  const outcomeConfig: Record<string, { label: string; cls: string }> = {
    TP_HIT: { label: "✓ TP Hit", cls: "bg-brand-green/20 text-brand-green border-brand-green/40" },
    SL_HIT: { label: "✗ SL Hit", cls: "bg-brand-red/20 text-brand-red border-brand-red/40" },
    UNKNOWN: { label: "? Unknown", cls: "bg-white/10 text-white/50 border-white/20" },
  };

  return (
    <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl shrink-0">
      {/* Mode Selector Tabs */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 pb-4 border-b border-white/10">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
            RLHF Human-in-the-Loop Review Queue
            {queueLoaded && totalPending > 0 && (
              <span className="text-xs sm:text-sm font-normal text-white/40 ml-2">
                {Math.min(currentOffset + 1, totalPending)} / {totalPending}
              </span>
            )}
          </h2>
          <p className="text-xs sm:text-sm text-white/50 mt-1">
            Kurasi sinyal Out-Of-Sample (OOS) secara terpisah untuk injeksi RLHF &amp; Hard Negatives.
          </p>
        </div>

        {/* Mode Switcher Tabs */}
        <div className="grid grid-cols-2 gap-1 p-1 bg-white/5 rounded-xl border border-white/10 w-full sm:w-auto">
          <button
            onClick={() => {
              setReviewMode("normal");
              setCurrentOffset(0);
              setQueueLoaded(false);
              setQueueDone(false);
              fetchSetup(0, minProb, "normal");
            }}
            className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
              reviewMode === "normal"
                ? "bg-cyan-500 text-black shadow-lg shadow-cyan-500/30"
                : "text-white/50 hover:text-white"
            }`}
          >
            ⚡ Normal (RR 1:2)
          </button>
          <button
            onClick={() => {
              setReviewMode("runner");
              setCurrentOffset(0);
              setQueueLoaded(false);
              setQueueDone(false);
              fetchSetup(0, minProb, "runner");
            }}
            className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
              reviewMode === "runner"
                ? "bg-purple-600 text-white shadow-lg shadow-purple-600/30"
                : "text-white/50 hover:text-white"
            }`}
          >
            🏹 Runner (RR 1:5)
          </button>
        </div>
      </div>

      {/* Filter Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-2 text-xs">
          <span className="text-white/40 font-mono">Target:</span>
          <span className={`px-2.5 py-1 rounded-md font-bold ${
            reviewMode === "normal" ? "bg-cyan-500/20 text-cyan-400" : "bg-purple-500/20 text-purple-400"
          }`}>
            {reviewMode === "normal" ? "Hit & Run (SL 1x ATR, TP 2x ATR)" : "Trend Runner (SL 1x ATR, TP 5x ATR)"}
          </span>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <span className="text-xs text-white/40 font-semibold">Min Prob:</span>
          <input
            type="range"
            min="0.50"
            max="0.99"
            step="0.01"
            value={minProb}
            onChange={(e) => setMinProb(parseFloat(e.target.value))}
            className="w-24 accent-brand-green"
          />
          <span className="text-white font-bold text-xs w-8 text-right font-mono">
            {(minProb * 100).toFixed(0)}%
          </span>
          <button
            onClick={() => {
              setCurrentOffset(0);
              setQueueLoaded(false);
              setQueueDone(false);
              fetchSetup(0, minProb, reviewMode);
            }}
            disabled={loading}
            className="bg-brand-green text-black px-4 py-2 rounded-xl font-bold text-xs transition-all disabled:opacity-50 flex items-center gap-1.5 shadow-md shadow-brand-green/20"
          >
            {loading ? <Loader2 className="animate-spin w-3.5 h-3.5" /> : "Load Queue"}
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      {queueLoaded && totalPending > 0 && (
        <div className="w-full h-1.5 rounded-full bg-white/10 mb-4 overflow-hidden">
          <div
            className="h-full rounded-full bg-brand-green transition-all duration-300"
            style={{ width: `${(currentOffset / totalPending) * 100}%` }}
          />
        </div>
      )}

      {/* Keyboard Shortcuts Hint */}
      {queueLoaded && currentSetup && (
        <div className="flex gap-3 mb-3 text-[10px] text-white/30 font-mono select-none">
          <span>A = Approve</span><span>·</span><span>I = Ignore</span><span>·</span><span>R = Reject</span><span>·</span><span>← → = Skip</span>
        </div>
      )}

      {/* Empty States */}
      {!queueLoaded && (
        <div className="text-center p-12 border border-dashed border-white/10 rounded-xl text-white/30 text-xs sm:text-sm">
          Atur probabilitas minimum dan klik <strong>Load Queue</strong> untuk mulai kurasi setup AI.
        </div>
      )}

      {queueLoaded && queueDone && (
        <div className="text-center p-12 border border-dashed border-brand-green/20 rounded-xl text-brand-green text-xs sm:text-sm font-semibold">
          🎉 Semua setup OOS dalam antrian telah selesai dikurasi!
        </div>
      )}

      {/* Active Setup Review Workspace */}
      {queueLoaded && !queueDone && currentSetup && (
        <div className="flex flex-col gap-4">
          {/* Setup Metadata Badges */}
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-3 py-1 rounded-full text-xs font-black tracking-wide border ${
              reviewMode === "normal"
                ? "bg-cyan-500/20 text-cyan-400 border-cyan-500/40"
                : "bg-purple-500/20 text-purple-400 border-purple-500/40"
            }`}>
              {reviewMode === "normal" ? "⚡ NORMAL (RR 1:2)" : "🏹 RUNNER (RR 1:5)"}
            </span>
            <span className={`px-3 py-1 rounded-full text-xs font-black ${
              currentSetup.action === "BUY" ? "bg-brand-green/20 text-brand-green border border-brand-green/30" : "bg-brand-red/20 text-brand-red border border-brand-red/30"
            }`}>
              {currentSetup.action} @ {currentSetup.price.toFixed(2)}
            </span>
            <span className="px-3 py-1 rounded-full text-xs font-bold bg-white/10 text-white/80 border border-white/10 font-mono">
              AI: {(currentSetup.probability * 100).toFixed(1)}%
            </span>
            {(() => {
              const oc = outcomeConfig[currentSetup.outcome] ?? outcomeConfig.UNKNOWN;
              return <span className={`px-3 py-1 rounded-full text-xs font-bold border ${oc.cls}`}>{oc.label}</span>;
            })()}
            <span className="text-xs text-white/40 ml-auto font-mono">{currentSetup.time}</span>
          </div>

          {/* Chart Review Canvas */}
          <div className="w-full rounded-xl overflow-hidden border border-white/10 bg-black/40 h-[280px] sm:h-[340px] md:h-[380px]">
            <SetupReviewChart
              candles={currentSetup.candles}
              entryPrice={currentSetup.price}
              entryTime={currentSetup.entry_time}
              sl={currentSetup.sl}
              tp={currentSetup.tp}
              action={currentSetup.action}
              tfLabel={currentSetup.tf_label}
            />
          </div>

          {/* Price Levels Strip */}
          <div className="flex flex-wrap items-center gap-3 text-xs px-1 text-white/60">
            <span className="text-brand-red font-mono">SL: <strong>{currentSetup.sl.toFixed(2)}</strong></span>
            <span>|</span>
            <span className="text-yellow-400 font-mono">Entry: <strong>{currentSetup.price.toFixed(2)}</strong></span>
            <span>|</span>
            <span className="text-brand-green font-mono">TP: <strong>{currentSetup.tp.toFixed(2)}</strong></span>
            <span className="ml-auto text-white/40">{currentSetup.tf_label} Resampled Candlestick</span>
          </div>

          {/* Notes Input */}
          <input
            ref={notesRef}
            type="text"
            value={rlhfNotes}
            onChange={(e) => setRlhfNotes(e.target.value)}
            placeholder="Catatan trader (opsional) — alasan kurasi setup ini..."
            className="w-full bg-white/5 border border-white/10 text-white rounded-xl px-4 py-2.5 text-xs sm:text-sm outline-none focus:border-brand-green transition-colors placeholder:text-white/20"
          />

          {/* Action Decision Controls */}
          <div className="flex gap-2 sm:gap-3 items-center">
            <button
              onClick={() => skipTo(-1)}
              disabled={loading || currentOffset === 0}
              className="p-3 rounded-xl bg-white/5 hover:bg-white/10 text-white/50 border border-white/10 transition-all disabled:opacity-30 shrink-0"
              title="Setup sebelumnya (←)"
            >
              <ChevronLeft size={16} />
            </button>

            <button
              onClick={() => submitDecision("approve")}
              disabled={loading}
              className="flex-1 bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/50 py-3 rounded-xl font-black text-xs sm:text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50"
            >
              <ThumbsUp size={16} /> Approve <span className="hidden sm:inline text-[10px] font-normal opacity-50">[A]</span>
            </button>

            <button
              onClick={() => submitDecision("ignore")}
              disabled={loading}
              className="flex-1 bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 py-3 rounded-xl font-black text-xs sm:text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50"
            >
              <MinusCircle size={16} /> Ignore <span className="hidden sm:inline text-[10px] font-normal opacity-50">[I]</span>
            </button>

            <button
              onClick={() => submitDecision("reject")}
              disabled={loading}
              className="flex-1 bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/50 py-3 rounded-xl font-black text-xs sm:text-sm flex items-center justify-center gap-2 transition-all disabled:opacity-50"
            >
              <ThumbsDown size={16} /> Reject <span className="hidden sm:inline text-[10px] font-normal opacity-50">[R]</span>
            </button>

            <button
              onClick={() => skipTo(1)}
              disabled={loading || currentOffset >= totalPending - 1}
              className="p-3 rounded-xl bg-white/5 hover:bg-white/10 text-white/50 border border-white/10 transition-all disabled:opacity-30 shrink-0"
              title="Lewati setup ini (→)"
            >
              <SkipForward size={16} />
            </button>
          </div>

          {loading && (
            <div className="flex items-center justify-center gap-2 text-white/40 text-xs py-1">
              <Loader2 className="animate-spin w-4 h-4" /> Memproses keputusan RLHF...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
