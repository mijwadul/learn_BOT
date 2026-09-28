"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { 
  ThumbsUp, 
  ThumbsDown, 
  MinusCircle, 
  ChevronLeft, 
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Loader2,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Layers,
  Sparkles,
  RefreshCw,
  Search
} from "lucide-react";
import dynamic from "next/dynamic";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";

const SetupReviewChart = dynamic(() => import("@/components/SetupReviewChart"), { ssr: false });

export interface CandleData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  sma_20?: number | null;
  bb_upper?: number | null;
  bb_lower?: number | null;
  ema_50?: number | null;
  lwma_5_h?: number | null;
  lwma_10_h?: number | null;
  lwma_5_l?: number | null;
  lwma_10_l?: number | null;
}

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
  candles?: CandleData[];
  entry_time: number;
  tf_label?: string;
  mode?: string;
  tp_multiplier?: number;
}

interface CurationStats {
  approved: number;
  rejected: number;
  ignored: number;
  total_curated: number;
}

interface RlhfReviewQueueProps {
  selectedPair?: string;
}

export function RlhfReviewQueue({ selectedPair = "XAUUSD" }: RlhfReviewQueueProps) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [loadingChart, setLoadingChart] = useState(false);
  const [reviewMode, setReviewMode] = useState<"normal" | "runner">("normal");
  const [minProb, setMinProb] = useState(0.65);
  const [currentTimeframe, setCurrentTimeframe] = useState<string>("M5");
  
  // Paginasi 10 data
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [totalPages, setTotalPages] = useState(1);
  const [totalPending, setTotalPending] = useState(0);
  const [stats, setStats] = useState<CurationStats>({ approved: 0, rejected: 0, ignored: 0, total_curated: 0 });
  
  // Daftar 10 setup untuk halaman ini
  const [setupsList, setSetupsList] = useState<Setup[]>([]);
  const [selectedSetupId, setSelectedSetupId] = useState<string | null>(null);
  const [activeSetup, setActiveSetup] = useState<Setup | null>(null);

  const [queueLoaded, setQueueLoaded] = useState(false);
  const [queueDone, setQueueDone] = useState(false);
  const [rlhfNotes, setRlhfNotes] = useState("");
  const notesRef = useRef<HTMLInputElement>(null);

  const activePair = (selectedPair || "XAUUSD").toUpperCase();

  // 1. Fetch 10 setup per halaman
  const fetchPage = useCallback(async (
    targetPage: number, 
    prob: number, 
    mode: "normal" | "runner", 
    sym: string,
    tf: string
  ) => {
    setLoading(true);
    try {
      const res = await fetch(
        `${getApiBaseUrl()}/api/rlhf/setups?min_prob=${prob}&page=${targetPage}&page_size=${pageSize}&mode=${mode}&symbol=${sym}&timeframe=${tf}`
      );
      const data = await res.json();

      if (data.status === "error") {
        toast.warning(data.message || "Gagal memuat queue RLHF.", "RLHF");
        setSetupsList([]);
        setActiveSetup(null);
        setTotalPending(0);
        setTotalPages(0);
        setQueueLoaded(true);
        return;
      }

      if (data.status === "done" || !data.setups || data.setups.length === 0) {
        setSetupsList([]);
        setActiveSetup(null);
        setTotalPending(0);
        setTotalPages(0);
        setQueueDone(true);
        if (data.stats) setStats(data.stats);
        toast.info(data.message ?? `Semua setup ${sym} selesai dikurasi!`, "RLHF Selesai");
      } else {
        setSetupsList(data.setups);
        setTotalPending(data.total_pending ?? data.total ?? 0);
        setTotalPages(data.total_pages || Math.ceil((data.total_pending || 1) / pageSize));
        setPage(data.page || targetPage);
        setQueueDone(false);
        if (data.stats) setStats(data.stats);

        // Pasang setup aktif
        const firstSetup = data.setup || data.setups[0];
        setActiveSetup(firstSetup);
        setSelectedSetupId(firstSetup.setup_id);
      }
      setQueueLoaded(true);
    } catch {
      toast.error(`Gagal terhubung ke backend untuk ${sym}.`, "Error Backend");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  // 2. Fetch candle chart khusus untuk setup tertentu & timeframe
  const fetchSetupChart = useCallback(async (setupId: string, sym: string, tf: string) => {
    setLoadingChart(true);
    try {
      const res = await fetch(
        `${getApiBaseUrl()}/api/rlhf/chart?setup_id=${encodeURIComponent(setupId)}&symbol=${sym}&timeframe=${tf}&mode=${reviewMode}`
      );
      const data = await res.json();
      if (data.status === "success" && data.candles) {
        setActiveSetup((prev) => {
          if (!prev || prev.setup_id !== setupId) return prev;
          return {
            ...prev,
            candles: data.candles,
            tf_label: data.timeframe || tf,
          };
        });
      } else {
        toast.warning(data.message || "Data chart tidak ditemukan.", "Chart");
      }
    } catch {
      toast.error("Gagal memuat chart timeframe.", "Error Chart");
    } finally {
      setLoadingChart(false);
    }
  }, [reviewMode, toast]);

  // Reset & load saat selectedPair atau reviewMode berganti
  useEffect(() => {
    setPage(1);
    setQueueLoaded(false);
    setQueueDone(false);
    setSetupsList([]);
    setActiveSetup(null);
    fetchPage(1, minProb, reviewMode, activePair, currentTimeframe);
  }, [activePair, reviewMode, minProb, fetchPage]); // eslint-disable-line react-hooks/exhaustive-deps

  // Ganti timeframe chart aktif
  const handleTimeframeChange = (tf: string) => {
    setCurrentTimeframe(tf);
    if (activeSetup) {
      fetchSetupChart(activeSetup.setup_id, activePair, tf);
    }
  };

  // Pilih baris setup dari tabel 10 data
  const handleSelectSetupRow = (setup: Setup) => {
    setSelectedSetupId(setup.setup_id);
    setActiveSetup(setup);
    // Jika setup belum punya candles untuk timeframe saat ini, fetch chart
    if (!setup.candles || setup.candles.length === 0 || setup.tf_label !== currentTimeframe) {
      fetchSetupChart(setup.setup_id, activePair, currentTimeframe);
    }
  };

  // Kirim keputusan kurasi (Approve / Reject / Ignore)
  const submitDecision = useCallback(async (
    targetSetup: Setup, 
    decision: "approve" | "reject" | "ignore"
  ) => {
    if (loading) return;
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/rlhf/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          setup_id: targetSetup.setup_id,
          symbol: targetSetup.symbol || activePair,
          action_type: targetSetup.action,
          probability: targetSetup.probability,
          decision,
          notes: rlhfNotes,
          mode: reviewMode,
        }),
      });
      const data = await res.json();
      if (data.status !== "success") {
        toast.error(data.message || "Gagal menyimpan feedback.", "Error");
        return;
      }

      if (decision === "approve") {
        toast.success(`Setup ${targetSetup.setup_id} disetujui [RLHF Approved].`, "Approved");
      } else if (decision === "reject") {
        toast.warning(`Setup ${targetSetup.setup_id} ditolak [RLHF Rejected].`, "Rejected");
      } else {
        toast.info(`Setup ${targetSetup.setup_id} diabaikan (Noise).`, "Ignored");
      }

      setRlhfNotes("");

      // Update daftar 10 data secara lokal
      const nextList = setupsList.filter((s) => s.setup_id !== targetSetup.setup_id);
      setSetupsList(nextList);
      setTotalPending((prev) => Math.max(0, prev - 1));
      setStats((prev) => ({
        ...prev,
        approved: prev.approved + (decision === "approve" ? 1 : 0),
        rejected: prev.rejected + (decision === "reject" ? 1 : 0),
        ignored: prev.ignored + (decision === "ignore" ? 1 : 0),
        total_curated: prev.total_curated + 1,
      }));

      if (nextList.length > 0) {
        // Pindah ke item berikutnya pada batch 10 ini
        const nextActive = nextList[0];
        setSelectedSetupId(nextActive.setup_id);
        setActiveSetup(nextActive);
        if (!nextActive.candles || nextActive.candles.length === 0) {
          fetchSetupChart(nextActive.setup_id, activePair, currentTimeframe);
        }
      } else {
        // Jika 10 data pada halaman ini habis dikurasi, refresh page
        fetchPage(page, minProb, reviewMode, activePair, currentTimeframe);
      }
    } catch {
      toast.error("Gagal mengirim feedback kurasi.", "Error");
    }
  }, [loading, rlhfNotes, reviewMode, activePair, setupsList, page, minProb, currentTimeframe, fetchPage, fetchSetupChart, toast]);

  // Keyboard shortcuts: A / R / I
  useEffect(() => {
    if (!queueLoaded || !activeSetup) return;
    const handler = (e: KeyboardEvent) => {
      if (document.activeElement === notesRef.current) return;
      if (e.key === "a" || e.key === "A") submitDecision(activeSetup, "approve");
      else if (e.key === "r" || e.key === "R") submitDecision(activeSetup, "reject");
      else if (e.key === "i" || e.key === "I") submitDecision(activeSetup, "ignore");
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [queueLoaded, activeSetup, submitDecision]);

  const outcomeConfig: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
    TP_HIT: { label: "TP Hit", icon: <CheckCircle2 size={12} />, cls: "bg-brand-green/20 text-brand-green border-brand-green/40" },
    SL_HIT: { label: "SL Hit", icon: <XCircle size={12} />, cls: "bg-brand-red/20 text-brand-red border-brand-red/40" },
    UNKNOWN: { label: "Unknown", icon: <HelpCircle size={12} />, cls: "bg-white/10 text-white/50 border-white/20" },
  };

  return (
    <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-4 sm:p-6 shadow-xl flex flex-col gap-5">
      {/* 1. Header & Mode Switcher */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2.5">
            <Layers className="text-cyan-400 w-5 h-5" />
            <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">
              RLHF Human-in-the-Loop Review Queue
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 font-mono font-bold border border-cyan-500/30">
              {activePair}
            </span>
          </div>
          <p className="text-xs text-white/50 mt-1">
            Kurasi setup AI khusus untuk pair <strong className="text-white">{activePair}</strong>. Data kurasi akan langsung dipelajari saat Incremental Training.
          </p>
        </div>

        {/* Mode Switcher Tabs (Normal vs Runner) */}
        <div className="flex items-center gap-1.5 p-1 bg-white/5 rounded-xl border border-white/10 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => {
              setReviewMode("normal");
              setPage(1);
            }}
            className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              reviewMode === "normal"
                ? "bg-cyan-500 text-black shadow-lg shadow-cyan-500/30 font-extrabold"
                : "text-white/60 hover:text-white"
            }`}
          >
            ⚡ Normal (RR 1:2)
          </button>
          <button
            type="button"
            onClick={() => {
              setReviewMode("runner");
              setPage(1);
            }}
            className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
              reviewMode === "runner"
                ? "bg-purple-600 text-white shadow-lg shadow-purple-600/30 font-extrabold"
                : "text-white/60 hover:text-white"
            }`}
          >
            🏹 Runner (RR 1:5)
          </button>
        </div>
      </div>

      {/* 2. Total Data & Curation Stats Banner (Point 4: Total Data Ditampilkan) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Total Harus Dikurasi */}
        <div className="bg-black/50 border border-cyan-500/30 rounded-xl p-3 flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-cyan-400/80 uppercase tracking-wider">
            Total Harus Dikurasi
          </span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-xl sm:text-2xl font-black text-white font-mono">
              {totalPending.toLocaleString()}
            </span>
            <span className="text-[11px] text-white/40">setup</span>
          </div>
          <span className="text-[10px] text-cyan-300/60 font-mono mt-1">
            Pair: {activePair} ({reviewMode.toUpperCase()})
          </span>
        </div>

        {/* Sudah Disetujui (Approved) */}
        <div className="bg-black/40 border border-emerald-500/20 rounded-xl p-3 flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1">
            <ThumbsUp size={12} /> Disetujui (Approve)
          </span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-xl sm:text-2xl font-black text-emerald-400 font-mono">
              {stats.approved.toLocaleString()}
            </span>
            <span className="text-[10px] text-emerald-400/50">bobot 5.0x</span>
          </div>
          <span className="text-[10px] text-white/40 font-mono mt-1">Diprioritaskan model</span>
        </div>

        {/* Sudah Ditolak (Rejected) */}
        <div className="bg-black/40 border border-rose-500/20 rounded-xl p-3 flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-rose-400 uppercase tracking-wider flex items-center gap-1">
            <ThumbsDown size={12} /> Ditolak (Reject)
          </span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-xl sm:text-2xl font-black text-rose-400 font-mono">
              {stats.rejected.toLocaleString()}
            </span>
            <span className="text-[10px] text-rose-400/50">penalti 0.1x</span>
          </div>
          <span className="text-[10px] text-white/40 font-mono mt-1">Ditekan agar tidak OP</span>
        </div>

        {/* Diabaikan (Ignored) */}
        <div className="bg-black/40 border border-amber-500/20 rounded-xl p-3 flex flex-col justify-between">
          <span className="text-[11px] font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1">
            <MinusCircle size={12} /> Diabaikan (Noise)
          </span>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-xl sm:text-2xl font-black text-amber-400 font-mono">
              {stats.ignored.toLocaleString()}
            </span>
            <span className="text-[10px] text-amber-400/50">dilewati</span>
          </div>
          <span className="text-[10px] text-white/40 font-mono mt-1">Tidak ikut training</span>
        </div>
      </div>

      {/* 3. Filter Bar: Min Probability + Refresh */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-white/[0.03] rounded-xl border border-white/5 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-white/50">Target Strategi:</span>
          <span className={`px-2 py-0.5 rounded font-bold text-[11px] ${
            reviewMode === "normal" ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30" : "bg-purple-500/20 text-purple-300 border border-purple-500/30"
          }`}>
            {reviewMode === "normal" ? "Scalp Hit & Run (1:2)" : "Trend Runner (1:5)"}
          </span>
          <span className="text-white/30 ml-2 font-mono">
            Halaman {page} dari {totalPages || 1} (10 setup per batch)
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-white/50 font-semibold">Min Probabilitas AI:</span>
            <input
              type="range"
              min="0.50"
              max="0.99"
              step="0.01"
              value={minProb}
              onChange={(e) => setMinProb(parseFloat(e.target.value))}
              className="w-24 accent-brand-green cursor-pointer"
            />
            <span className="text-white font-bold font-mono w-10 text-right">
              {(minProb * 100).toFixed(0)}%
            </span>
          </div>

          <button
            type="button"
            onClick={() => fetchPage(page, minProb, reviewMode, activePair, currentTimeframe)}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/40 font-bold flex items-center gap-1.5 transition-all disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            <span>Muat Ulang</span>
          </button>
        </div>
      </div>

      {/* Empty States */}
      {queueLoaded && totalPending === 0 && (
        <div className="text-center p-12 border border-dashed border-brand-green/30 rounded-2xl bg-brand-green/5 text-brand-green text-sm font-semibold">
          🎉 Seluruh setup OOS {activePair} ({reviewMode.toUpperCase()}) dengan probabilitas $\ge$ {(minProb * 100).toFixed(0)}% telah selesai dikurasi!
        </div>
      )}

      {/* 4. Active Setup Workspace (Chart + Decision Bar) */}
      {activeSetup && (
        <div className="bg-black/60 border border-white/10 rounded-2xl p-4 flex flex-col gap-4 shadow-2xl">
          {/* Active Setup Ribbon */}
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/10">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`px-2.5 py-1 rounded-lg text-xs font-black tracking-wider border ${
                activeSetup.action === "BUY"
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                  : "bg-rose-500/20 text-rose-400 border-rose-500/40"
              }`}>
                {activeSetup.action} @ {activeSetup.price.toFixed(2)}
              </span>

              <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-white/10 text-white/90 border border-white/10 font-mono">
                AI Prob: {(activeSetup.probability * 100).toFixed(1)}%
              </span>

              {(() => {
                const oc = outcomeConfig[activeSetup.outcome] ?? outcomeConfig.UNKNOWN;
                return (
                  <span className={`px-2.5 py-1 rounded-lg text-xs font-bold border flex items-center gap-1 ${oc.cls}`}>
                    {oc.icon} {oc.label}
                  </span>
                );
              })()}

              <span className="text-xs text-white/40 font-mono ml-2">
                ID: {activeSetup.setup_id}
              </span>
            </div>

            {/* Quick Levels Info */}
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="text-rose-400">SL: {activeSetup.sl.toFixed(2)}</span>
              <span className="text-white/20">|</span>
              <span className="text-yellow-300">Entry: {activeSetup.price.toFixed(2)}</span>
              <span className="text-white/20">|</span>
              <span className="text-emerald-400">TP: {activeSetup.tp.toFixed(2)} ({activeSetup.tp_multiplier || (reviewMode === "normal" ? 2 : 5)}x ATR)</span>
            </div>
          </div>

          {/* Interactive Chart Canvas (Point 1: Pindah Timeframe, Point 2: Indikator BBMA) */}
          <div className="w-full h-[320px] sm:h-[380px] md:h-[420px] rounded-xl overflow-hidden border border-white/10 bg-black/40">
            <SetupReviewChart
              candles={activeSetup.candles || []}
              entryPrice={activeSetup.price}
              entryTime={activeSetup.entry_time}
              sl={activeSetup.sl}
              tp={activeSetup.tp}
              action={activeSetup.action}
              tfLabel={activeSetup.tf_label || currentTimeframe}
              currentTimeframe={currentTimeframe}
              onTimeframeChange={handleTimeframeChange}
              isLoadingTf={loadingChart}
            />
          </div>

          {/* Notes Input & Kurasi Action Bar */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-2">
            <input
              ref={notesRef}
              type="text"
              value={rlhfNotes}
              onChange={(e) => setRlhfNotes(e.target.value)}
              placeholder="Catatan trader (opsional) — alasan kurasi setup ini..."
              className="flex-1 bg-white/5 border border-white/10 text-white rounded-xl px-4 py-2.5 text-xs outline-none focus:border-brand-green transition-colors placeholder:text-white/20"
            />

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => submitDecision(activeSetup, "approve")}
                disabled={loading}
                className="px-4 py-2.5 rounded-xl bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/50 text-xs font-black flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
                title="Setujui setup (Shortcut: A)"
              >
                <ThumbsUp size={14} /> Approve <span className="text-[10px] opacity-60 font-mono">[A]</span>
              </button>

              <button
                type="button"
                onClick={() => submitDecision(activeSetup, "ignore")}
                disabled={loading}
                className="px-4 py-2.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-xs font-black flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
                title="Abaikan sebagai noise (Shortcut: I)"
              >
                <MinusCircle size={14} /> Ignore <span className="text-[10px] opacity-60 font-mono">[I]</span>
              </button>

              <button
                type="button"
                onClick={() => submitDecision(activeSetup, "reject")}
                disabled={loading}
                className="px-4 py-2.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/50 text-xs font-black flex items-center gap-1.5 transition-all cursor-pointer disabled:opacity-50"
                title="Tolak setup (Shortcut: R)"
              >
                <ThumbsDown size={14} /> Reject <span className="text-[10px] opacity-60 font-mono">[R]</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. Tabel Batch 10 Data (Point 5: Data ditampilkan tiap 10 data) */}
      {setupsList.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <Sparkles size={14} className="text-brand-green" /> Daftar 10 Setup Halaman Ini ({setupsList.length} data)
            </h3>
            <span className="text-xs text-white/40 font-mono">
              Klik baris untuk memeriksa chart &amp; indikator BBMA
            </span>
          </div>

          <div className="overflow-x-auto rounded-xl border border-white/10 bg-black/40">
            <table className="w-full text-xs text-left text-white/80">
              <thead className="text-[11px] uppercase bg-white/5 text-white/50 border-b border-white/10 font-mono">
                <tr>
                  <th className="py-2.5 px-3">#</th>
                  <th className="py-2.5 px-3">Waktu (Setup ID)</th>
                  <th className="py-2.5 px-3">Arah</th>
                  <th className="py-2.5 px-3">Prob AI</th>
                  <th className="py-2.5 px-3">Entry</th>
                  <th className="py-2.5 px-3">SL / TP</th>
                  <th className="py-2.5 px-3">Outcome</th>
                  <th className="py-2.5 px-3 text-right">Aksi Cepat</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 font-mono">
                {setupsList.map((setup, idx) => {
                  const isSelected = selectedSetupId === setup.setup_id;
                  const oc = outcomeConfig[setup.outcome] ?? outcomeConfig.UNKNOWN;
                  const itemNumber = (page - 1) * pageSize + idx + 1;

                  return (
                    <tr
                      key={setup.setup_id}
                      onClick={() => handleSelectSetupRow(setup)}
                      className={`transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-brand-green/10 border-l-2 border-brand-green text-white"
                          : "hover:bg-white/[0.03]"
                      }`}
                    >
                      <td className="py-2.5 px-3 font-bold text-white/40">
                        {itemNumber}
                      </td>
                      <td className="py-2.5 px-3 font-sans font-semibold text-white">
                        {setup.time}
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          setup.action === "BUY"
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                            : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                        }`}>
                          {setup.action}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-cyan-300 font-bold">
                        {(setup.probability * 100).toFixed(1)}%
                      </td>
                      <td className="py-2.5 px-3 text-yellow-300">
                        {setup.price.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-3 text-white/60">
                        <span className="text-rose-400">{setup.sl.toFixed(2)}</span> / <span className="text-emerald-400">{setup.tp.toFixed(2)}</span>
                      </td>
                      <td className="py-2.5 px-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border inline-flex items-center gap-1 ${oc.cls}`}>
                          {oc.icon} {oc.label}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="inline-flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => submitDecision(setup, "approve")}
                            className="p-1.5 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 transition-all"
                            title="Approve setup ini"
                          >
                            <ThumbsUp size={12} />
                          </button>
                          <button
                            type="button"
                            onClick={() => submitDecision(setup, "ignore")}
                            className="p-1.5 rounded-lg bg-amber-500/10 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 transition-all"
                            title="Ignore setup ini"
                          >
                            <MinusCircle size={12} />
                          </button>
                          <button
                            type="button"
                            onClick={() => submitDecision(setup, "reject")}
                            className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/25 text-rose-400 border border-rose-500/30 transition-all"
                            title="Reject setup ini"
                          >
                            <ThumbsDown size={12} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* 6. Paginasi Kontrol (10 data per halaman) */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-xs">
            <span className="text-white/40 font-mono">
              Menampilkan {setupsList.length} data (Halaman {page} dari {totalPages}) · Sisa {totalPending.toLocaleString()} setup
            </span>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setPage(1);
                  fetchPage(1, minProb, reviewMode, activePair, currentTimeframe);
                }}
                disabled={loading || page <= 1}
                className="px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/60 hover:text-white border border-white/10 transition-all disabled:opacity-30 cursor-pointer flex items-center gap-1"
                title="Halaman Pertama"
              >
                <ChevronsLeft size={14} /> <span className="hidden sm:inline">Pertama</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  const prevPage = Math.max(1, page - 1);
                  setPage(prevPage);
                  fetchPage(prevPage, minProb, reviewMode, activePair, currentTimeframe);
                }}
                disabled={loading || page <= 1}
                className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/60 hover:text-white border border-white/10 transition-all disabled:opacity-30 cursor-pointer flex items-center gap-1 font-semibold"
              >
                <ChevronLeft size={14} /> 10 Sebelumnya
              </button>

              <span className="px-3 py-1.5 rounded-lg bg-black/60 border border-white/10 font-bold font-mono text-cyan-300">
                {page} / {totalPages}
              </span>

              <button
                type="button"
                onClick={() => {
                  const nextPage = Math.min(totalPages, page + 1);
                  setPage(nextPage);
                  fetchPage(nextPage, minProb, reviewMode, activePair, currentTimeframe);
                }}
                disabled={loading || page >= totalPages}
                className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/60 hover:text-white border border-white/10 transition-all disabled:opacity-30 cursor-pointer flex items-center gap-1 font-semibold"
              >
                10 Berikutnya <ChevronRight size={14} />
              </button>

              <button
                type="button"
                onClick={() => {
                  setPage(totalPages);
                  fetchPage(totalPages, minProb, reviewMode, activePair, currentTimeframe);
                }}
                disabled={loading || page >= totalPages}
                className="px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/60 hover:text-white border border-white/10 transition-all disabled:opacity-30 cursor-pointer flex items-center gap-1"
                title="Halaman Terakhir"
              >
                <span className="hidden sm:inline">Terakhir</span> <ChevronsRight size={14} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
