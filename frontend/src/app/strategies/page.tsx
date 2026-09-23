"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Settings2, ShieldAlert, Zap, BrainCircuit, ThumbsUp, ThumbsDown, Loader2, ChevronLeft, MinusCircle, SkipForward } from "lucide-react";
import dynamic from "next/dynamic";
import { getApiBaseUrl } from "@/config";

// Dynamic import agar chart tidak di-SSR (lightweight-charts butuh window)
const SetupReviewChart = dynamic(() => import("@/components/SetupReviewChart"), { ssr: false });

interface Setup {
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

export default function StrategiesPage() {
  const [loading, setLoading] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);
  const [rlhfNotes, setRlhfNotes] = useState("");
  const notesRef = useRef<HTMLInputElement>(null);

  const [modelsStatus, setModelsStatus] = useState({
    normal: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0 },
    runner: { trained: false, status: "IDLE/QUARANTINE", is_training: false, last_accuracy: 0.0 }
  });

  useEffect(() => {
    const fetchStatus = () => {
      fetch(`${getApiBaseUrl()}/api/state`)
        .then(res => res.json())
        .then(data => { if (data.models_status) setModelsStatus(data.models_status); })
        .catch(err => console.error(err));
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const forceMode = async (mode: string, action: "force_live" | "quarantine") => {
    setLoading(true);
    try {
      const endpoint = action === "force_live" ? "/api/strategies/force_live" : "/api/strategies/quarantine";
      const res = await fetch(`${getApiBaseUrl()}${endpoint}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode })
      });
      const data = await res.json();
      setLastAction(`[${action.toUpperCase()}] applied to ${mode.toUpperCase()}. State: ${data.state}`);
    } catch { setLastAction(`Error: Failed to connect to backend.`); }
    setLoading(false);
  };

  const trainMode = async (mode: string, type: "incremental" | "full") => {
    setLoading(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/train`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, type })
      });
      const data = await res.json();
      setLastAction(data.message);
    } catch { setLastAction(`Error: Failed to trigger training.`); }
    setLoading(false);
  };

  // ===== RLHF REVIEW QUEUE STATE =====
  const [reviewMode, setReviewMode] = useState<"normal" | "runner">("normal");
  const [currentSetup, setCurrentSetup] = useState<Setup | null>(null);
  const [totalPending, setTotalPending] = useState(0);
  const [currentOffset, setCurrentOffset] = useState(0);
  const [minProb, setMinProb] = useState(0.65);
  const [queueLoaded, setQueueLoaded] = useState(false);
  const [queueDone, setQueueDone] = useState(false);

  const fetchSetup = useCallback(async (offset: number, prob: number, mode: "normal" | "runner") => {
    setLoading(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/rlhf/setups?min_prob=${prob}&offset=${offset}&mode=${mode}`);
      const data = await res.json();
      if (data.status === "done" || !data.setup) {
        setCurrentSetup(null);
        setTotalPending(data.total ?? 0);
        setQueueDone(true);
        setLastAction(data.message ?? "Antrian selesai.");
      } else {
        setCurrentSetup(data.setup);
        setTotalPending(data.total);
        setQueueDone(false);
        setLastAction(null);
      }
      setQueueLoaded(true);
    } catch { setLastAction("Error: Gagal terhubung ke backend."); }
    setLoading(false);
  }, []);

  const submitDecision = useCallback(async (decision: "approve" | "reject" | "ignore") => {
    if (!currentSetup || loading) return;
    setLoading(true);
    try {
      await fetch(`${getApiBaseUrl()}/api/rlhf/feedback`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          setup_id: currentSetup.setup_id, symbol: currentSetup.symbol,
          action_type: currentSetup.action, probability: currentSetup.probability,
          decision, notes: rlhfNotes, mode: reviewMode
        })
      });
      setRlhfNotes("");
      const next = currentOffset + 1;
      setCurrentOffset(next);
      fetchSetup(next, minProb, reviewMode);
    } catch { setLastAction("Error: Gagal menyimpan keputusan."); setLoading(false); }
  }, [currentSetup, loading, rlhfNotes, currentOffset, minProb, reviewMode, fetchSetup]);

  const skipTo = useCallback((delta: number) => {
    if (loading) return;
    const next = Math.max(0, Math.min(currentOffset + delta, totalPending - 1));
    setCurrentOffset(next);
    fetchSetup(next, minProb, reviewMode);
  }, [loading, currentOffset, totalPending, minProb, reviewMode, fetchSetup]);

  // Keyboard shortcuts: A/I/R/←/→
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
    TP_HIT:  { label: "✓ TP Hit",  cls: "bg-brand-green/20 text-brand-green border-brand-green/40" },
    SL_HIT:  { label: "✗ SL Hit",  cls: "bg-brand-red/20 text-brand-red border-brand-red/40" },
    UNKNOWN: { label: "? Unknown", cls: "bg-white/10 text-white/50 border-white/20" },
  };

  return (
    <div className="p-3 sm:p-4 md:p-6 min-h-full flex flex-col">
      <div className="mb-6 md:mb-8 shrink-0">
        <h1 className="text-2xl sm:text-3xl font-black text-white tracking-widest flex items-center gap-2 sm:gap-3">
          <Settings2 className="text-brand-green" /> STRATEGIES &amp; INCUBATOR
        </h1>
        <p className="text-white/50 text-xs sm:text-sm mt-1">Manage execution modes, AI Training, and RLHF Feedback (Phase 3)</p>
      </div>

      {lastAction && (
        <div className="mb-4 sm:mb-6 p-3 sm:p-4 rounded-xl bg-brand-blue/20 border border-brand-blue/50 text-brand-blue text-xs sm:text-sm font-medium shrink-0">
          {lastAction}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6 mb-6 md:mb-8 shrink-0">
        {/* Normal Mode */}
        <div className="glass-panel p-4 sm:p-6 flex flex-col justify-between">
          <div>
            <h2 className="text-lg sm:text-xl font-bold text-white mb-1 sm:mb-2">Normal Mode (Scalping)</h2>
            <p className="text-xs sm:text-sm text-white/50 mb-2">Aggressive intraday trading. Optimized on H1 data.</p>
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mb-4 sm:mb-6 text-[11px] sm:text-xs font-bold">
              <span className={`px-2 py-0.5 sm:py-1 rounded-full ${modelsStatus.normal.trained ? 'bg-brand-blue/20 text-brand-blue' : 'bg-white/10 text-white/50'}`}>{modelsStatus.normal.trained ? 'TRAINED' : 'UNTRAINED'}</span>
              <span className={`px-2 py-0.5 sm:py-1 rounded-full ${modelsStatus.normal.status.includes('LIVE') ? 'bg-brand-green/20 text-brand-green' : 'bg-brand-red/20 text-brand-red'}`}>{modelsStatus.normal.status}</span>
              {modelsStatus.normal.trained && <span className={`px-2 py-0.5 sm:py-1 rounded-full ${modelsStatus.normal.last_accuracy > 0.5 ? 'bg-brand-green/20 text-brand-green' : 'bg-orange-500/20 text-orange-400'}`}>Acc: {(modelsStatus.normal.last_accuracy * 100).toFixed(1)}%</span>}
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:gap-3">
            <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
              <button disabled={loading || modelsStatus.normal.is_training} onClick={() => trainMode("normal", "incremental")} className="flex-1 bg-brand-blue/20 hover:bg-brand-blue/30 text-brand-blue border border-brand-blue/50 p-2.5 sm:p-3.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs sm:text-sm disabled:opacity-50">
                {modelsStatus.normal.is_training ? <><Loader2 className="animate-spin" size={16}/>Training...</> : <><BrainCircuit size={16} /> Incremental Train</>}
              </button>
              <button disabled={loading || modelsStatus.normal.is_training} onClick={() => trainMode("normal", "full")} className="flex-1 bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 border border-purple-500/50 p-2.5 sm:p-3.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs sm:text-sm disabled:opacity-50">
                {modelsStatus.normal.is_training ? <><Loader2 className="animate-spin" size={16}/>Training...</> : "Force Full Train"}
              </button>
            </div>
            <div className="flex gap-2 sm:gap-3">
              <button disabled={loading} onClick={() => forceMode("normal", "force_live")} className="flex-1 bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/50 p-2.5 sm:p-3.5 rounded-xl font-bold flex items-center justify-center gap-1.5 sm:gap-2 transition-all text-xs sm:text-sm"><Zap size={18} /> Force LIVE</button>
              <button disabled={loading} onClick={() => forceMode("normal", "quarantine")} className="flex-1 bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/50 p-2.5 sm:p-3.5 rounded-xl font-bold flex items-center justify-center gap-1.5 sm:gap-2 transition-all text-xs sm:text-sm"><ShieldAlert size={18} /> Quarantine</button>
            </div>
          </div>
        </div>

        {/* Runner Mode */}
        <div className="glass-panel p-4 sm:p-6 flex flex-col justify-between">
          <div>
            <h2 className="text-lg sm:text-xl font-bold text-white mb-1 sm:mb-2">Runner Mode (Trend)</h2>
            <p className="text-xs sm:text-sm text-white/50 mb-2">Long term position holding. Optimized on full H4 data.</p>
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mb-4 sm:mb-6 text-[11px] sm:text-xs font-bold">
              <span className={`px-2 py-0.5 sm:py-1 rounded-full ${modelsStatus.runner.trained ? 'bg-brand-blue/20 text-brand-blue' : 'bg-white/10 text-white/50'}`}>{modelsStatus.runner.trained ? 'TRAINED' : 'UNTRAINED'}</span>
              <span className={`px-2 py-0.5 sm:py-1 rounded-full ${modelsStatus.runner.status.includes('LIVE') ? 'bg-brand-green/20 text-brand-green' : 'bg-brand-red/20 text-brand-red'}`}>{modelsStatus.runner.status}</span>
              {modelsStatus.runner.trained && <span className={`px-2 py-0.5 sm:py-1 rounded-full ${modelsStatus.runner.last_accuracy > 0.5 ? 'bg-brand-green/20 text-brand-green' : 'bg-orange-500/20 text-orange-400'}`}>Acc: {(modelsStatus.runner.last_accuracy * 100).toFixed(1)}%</span>}
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:gap-3">
            <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
              <button disabled={loading || modelsStatus.runner.is_training} onClick={() => trainMode("runner", "incremental")} className="flex-1 bg-brand-blue/20 hover:bg-brand-blue/30 text-brand-blue border border-brand-blue/50 p-2.5 sm:p-3.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs sm:text-sm disabled:opacity-50">
                {modelsStatus.runner.is_training ? <><Loader2 className="animate-spin" size={16}/>Training...</> : <><BrainCircuit size={16} /> Incremental Train</>}
              </button>
              <button disabled={loading || modelsStatus.runner.is_training} onClick={() => trainMode("runner", "full")} className="flex-1 bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 border border-purple-500/50 p-2.5 sm:p-3.5 rounded-xl font-bold flex items-center justify-center gap-2 transition-all text-xs sm:text-sm disabled:opacity-50">
                {modelsStatus.runner.is_training ? <><Loader2 className="animate-spin" size={16}/>Training...</> : "Force Full Train"}
              </button>
            </div>
            <div className="flex gap-2 sm:gap-3">
              <button disabled={loading} onClick={() => forceMode("runner", "force_live")} className="flex-1 bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/50 p-2.5 sm:p-3.5 rounded-xl font-bold flex items-center justify-center gap-1.5 sm:gap-2 transition-all text-xs sm:text-sm"><Zap size={18} /> Force LIVE</button>
              <button disabled={loading} onClick={() => forceMode("runner", "quarantine")} className="flex-1 bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/50 p-2.5 sm:p-3.5 rounded-xl font-bold flex items-center justify-center gap-1.5 sm:gap-2 transition-all text-xs sm:text-sm"><ShieldAlert size={18} /> Quarantine</button>
            </div>
          </div>
        </div>
      </div>

      {/* ===== RLHF REVIEW QUEUE ===== */}
      <div className="glass-panel p-4 sm:p-6 shrink-0">
        {/* Mode Selector Tabs */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 pb-4 border-b border-white/10">
          <div>
            <h2 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
              RLHF Review Queue
              {queueLoaded && totalPending > 0 && (
                <span className="text-xs sm:text-sm font-normal text-white/40 ml-2">{Math.min(currentOffset + 1, totalPending)} / {totalPending}</span>
              )}
            </h2>
            <p className="text-xs sm:text-sm text-white/50 mt-1">Kurasi setup OOS secara terpisah — AI Normal &amp; Runner dilatih tepat sasaran.</p>
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
              className={`px-3 py-2 rounded-lg text-[11px] sm:text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                reviewMode === "normal"
                  ? "bg-brand-blue text-white shadow-lg shadow-brand-blue/30"
                  : "text-white/50 hover:text-white hover:bg-white/5"
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
              className={`px-3 py-2 rounded-lg text-[11px] sm:text-xs font-bold transition-all flex items-center justify-center gap-1.5 ${
                reviewMode === "runner"
                  ? "bg-purple-600 text-white shadow-lg shadow-purple-600/30"
                  : "text-white/50 hover:text-white hover:bg-white/5"
              }`}
            >
              🏹 Runner (RR 1:5)
            </button>
          </div>
        </div>

        {/* Filter row */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-white/40 font-mono">Target Aktif:</span>
            <span className={`px-2 py-0.5 rounded font-bold ${reviewMode === 'normal' ? 'bg-cyan-500/20 text-cyan-400' : 'bg-purple-500/20 text-purple-400'}`}>
              {reviewMode === 'normal' ? 'Hit & Run (SL 1x ATR, TP 2x ATR)' : 'Trend Runner (SL 1x ATR, TP 5x ATR)'}
            </span>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <span className="text-xs text-white/40">Min Prob</span>
            <input type="range" min="0.50" max="0.99" step="0.01" value={minProb} onChange={e => setMinProb(parseFloat(e.target.value))} className="w-24" />
            <span className="text-white font-bold text-sm w-10 text-right">{(minProb * 100).toFixed(0)}%</span>
            <button
              onClick={() => { setCurrentOffset(0); setQueueLoaded(false); setQueueDone(false); fetchSetup(0, minProb, reviewMode); }}
              disabled={loading}
              className="bg-brand-blue/20 hover:bg-brand-blue/30 text-brand-blue border border-brand-blue/50 px-5 py-2 rounded-xl font-bold text-sm transition-all disabled:opacity-50 flex items-center gap-2"
            >
              {loading ? <Loader2 className="animate-spin" size={16} /> : "Load Queue"}
            </button>
          </div>
        </div>

        {/* Progress bar */}
        {queueLoaded && totalPending > 0 && (
          <div className="w-full h-1 rounded-full bg-white/10 mb-5 overflow-hidden">
            <div className="h-full rounded-full bg-brand-blue transition-all duration-300" style={{ width: `${(currentOffset / totalPending) * 100}%` }} />
          </div>
        )}

        {/* Keyboard hint */}
        {queueLoaded && currentSetup && (
          <div className="flex gap-3 mb-4 text-[10px] text-white/25 font-mono select-none">
            <span>A = Approve</span><span>·</span><span>I = Ignore</span><span>·</span><span>R = Reject</span><span>·</span><span>← → = Skip</span>
          </div>
        )}

        {/* States */}
        {!queueLoaded && (
          <div className="text-center p-12 border border-dashed border-white/10 rounded-xl text-white/30 text-sm">
            Atur probabilitas minimum dan klik <strong>Load Queue</strong> untuk mulai kurasi.
          </div>
        )}

        {queueLoaded && queueDone && (
          <div className="text-center p-12 border border-dashed border-brand-green/20 rounded-xl text-brand-green/60 text-sm">
            🎉 Semua setup dalam antrian sudah dikurasi!
          </div>
        )}

        {queueLoaded && !queueDone && currentSetup && (
          <div className="flex flex-col gap-4">
            {/* Setup info */}
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-3 py-1.5 rounded-full text-xs font-black tracking-wide border ${
                reviewMode === 'normal'
                  ? 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40'
                  : 'bg-purple-500/20 text-purple-400 border-purple-500/40'
              }`}>
                {reviewMode === 'normal' ? '⚡ NORMAL (RR 1:2)' : '🏹 RUNNER (RR 1:5)'}
              </span>
              <span className={`px-3 py-1.5 rounded-full text-sm font-black ${currentSetup.action === 'BUY' ? 'bg-brand-green/20 text-brand-green border border-brand-green/30' : 'bg-brand-red/20 text-brand-red border border-brand-red/30'}`}>
                {currentSetup.action} @ {currentSetup.price.toFixed(2)}
              </span>
              <span className="px-3 py-1.5 rounded-full text-sm font-bold bg-brand-blue/20 text-brand-blue border border-brand-blue/30">
                AI: {(currentSetup.probability * 100).toFixed(1)}%
              </span>
              {(() => {
                const oc = outcomeConfig[currentSetup.outcome] ?? outcomeConfig.UNKNOWN;
                return <span className={`px-3 py-1.5 rounded-full text-xs font-bold border ${oc.cls}`}>{oc.label}</span>;
              })()}
              <span className="text-xs text-white/30 ml-auto font-mono">{currentSetup.time}</span>
            </div>

            {/* Chart */}
            <div className="w-full rounded-xl overflow-hidden border border-white/10 bg-black/30 h-[280px] sm:h-[340px] md:h-[380px]">
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

            {/* SL / Entry / TP strip */}
            <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-[11px] sm:text-xs px-1">
              <span className="text-brand-red/80">SL <strong>{currentSetup.sl.toFixed(2)}</strong></span>
              <span className="text-white/20">|</span>
              <span className="text-yellow-400/80">Entry <strong>{currentSetup.price.toFixed(2)}</strong></span>
              <span className="text-white/20">|</span>
              <span className="text-brand-green/80">TP <strong>{currentSetup.tp.toFixed(2)}</strong></span>
              <span className="text-white/20 ml-auto">|</span>
              <span className="text-white/40">{currentSetup.tf_label} Chart</span>
            </div>

            {/* Notes input */}
            <input
              ref={notesRef}
              type="text"
              value={rlhfNotes}
              onChange={e => setRlhfNotes(e.target.value)}
              placeholder="Catatan (opsional) — alasan keputusan Anda..."
              className="w-full bg-black/40 border border-white/10 text-white rounded-xl px-3 sm:px-4 py-2.5 sm:py-3 text-xs sm:text-sm outline-none focus:border-brand-blue transition-colors placeholder:text-white/20"
            />

            {/* Action row */}
            <div className="flex gap-1.5 sm:gap-3 items-center">
              <button onClick={() => skipTo(-1)} disabled={loading || currentOffset === 0}
                className="p-2.5 sm:p-3 rounded-xl bg-white/5 hover:bg-white/10 text-white/50 border border-white/10 transition-all disabled:opacity-30 shrink-0" title="Setup sebelumnya (←)">
                <ChevronLeft size={16} />
              </button>

              <button onClick={() => submitDecision("approve")} disabled={loading}
                className="flex-1 bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/50 py-2.5 sm:py-3.5 rounded-xl font-black text-xs sm:text-sm flex items-center justify-center gap-1 sm:gap-2 transition-all disabled:opacity-50">
                <ThumbsUp size={15} /> Approve <span className="hidden sm:inline text-[10px] font-normal opacity-40 ml-1">[A]</span>
              </button>

              <button onClick={() => submitDecision("ignore")} disabled={loading}
                className="flex-1 bg-yellow-500/10 hover:bg-yellow-500/20 text-yellow-400 border border-yellow-500/30 py-2.5 sm:py-3.5 rounded-xl font-black text-xs sm:text-sm flex items-center justify-center gap-1 sm:gap-2 transition-all disabled:opacity-50">
                <MinusCircle size={15} /> Ignore <span className="hidden sm:inline text-[10px] font-normal opacity-40 ml-1">[I]</span>
              </button>

              <button onClick={() => submitDecision("reject")} disabled={loading}
                className="flex-1 bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/50 py-2.5 sm:py-3.5 rounded-xl font-black text-xs sm:text-sm flex items-center justify-center gap-1 sm:gap-2 transition-all disabled:opacity-50">
                <ThumbsDown size={15} /> Reject <span className="hidden sm:inline text-[10px] font-normal opacity-40 ml-1">[R]</span>
              </button>

              <button onClick={() => skipTo(1)} disabled={loading || currentOffset >= totalPending - 1}
                className="p-2.5 sm:p-3 rounded-xl bg-white/5 hover:bg-white/10 text-white/50 border border-white/10 transition-all disabled:opacity-30 shrink-0" title="Lewati tanpa keputusan (→)">
                <SkipForward size={16} />
              </button>
            </div>

            {loading && (
              <div className="flex items-center justify-center gap-2 text-white/40 text-sm py-1">
                <Loader2 className="animate-spin" size={16} /> Memproses...
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
