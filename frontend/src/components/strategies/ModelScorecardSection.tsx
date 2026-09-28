"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  HelpCircle,
  Play,
  RotateCw,
  Loader2,
  TrendingUp,
  History,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  BarChart3,
  Calendar,
  Layers,
} from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import EquityCurveChart, { EquityPoint } from "./EquityCurveChart";

interface ScorecardMetric {
  win_rate_pct: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  total_trades: number;
  total_return_pct: number;
}

interface ScorecardData {
  id?: number;
  symbol: string;
  mode: string;
  evaluated_at?: string;
  trained_at?: string;
  passed?: boolean;
  threshold_used?: number;
  metrics?: ScorecardMetric;
  total_trades?: number;
  win_rate_pct?: number;
  profit_factor?: number;
  sharpe_ratio?: number;
  max_drawdown_pct?: number;
  total_return_pct?: number;
  criteria?: Record<string, number>;
  checks?: Record<string, boolean>;
  reasons?: string[];
  failure_reason?: string;
  oos_start_date?: string;
  oos_end_date?: string;
  equity_curve?: EquityPoint[];
}

interface ModelScorecardSectionProps {
  selectedPair: string;
}

export function ModelScorecardSection({ selectedPair }: ModelScorecardSectionProps) {
  const toast = useToast();
  const [loadingLatest, setLoadingLatest] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [evaluating, setEvaluating] = useState(false);

  const [latestScorecards, setLatestScorecards] = useState<{
    normal: ScorecardData | null;
    runner: ScorecardData | null;
  }>({ normal: null, runner: null });

  // History state
  const [historyItems, setHistoryItems] = useState<ScorecardData[]>([]);
  const [historyMode, setHistoryMode] = useState<string>("all");
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalRecords, setTotalRecords] = useState<number>(0);

  // Active equity curve mode tab
  const [activeCurveTab, setActiveCurveTab] = useState<"normal" | "runner">("normal");

  // Fetch Latest Scorecards
  const fetchLatestScorecards = useCallback(async (sym = selectedPair) => {
    setLoadingLatest(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/scorecard/latest?symbol=${sym}`);
      const data = await res.json();
      if (data.status === "success" && data.latest) {
        setLatestScorecards({
          normal: data.latest.normal ?? null,
          runner: data.latest.runner ?? null,
        });
      }
    } catch (err) {
      console.error("Gagal mengambil latest scorecard:", err);
    } finally {
      setLoadingLatest(false);
    }
  }, [selectedPair]);

  // Fetch Scorecard History (Paginated)
  const fetchScorecardHistory = useCallback(
    async (sym = selectedPair, mode = historyMode, pageNum = page) => {
      setLoadingHistory(true);
      try {
        const modeParam = mode !== "all" ? `&mode=${mode}` : "";
        const res = await fetch(
          `${getApiBaseUrl()}/api/strategies/scorecard?symbol=${sym}${modeParam}&page=${pageNum}&limit=10`
        );
        const data = await res.json();
        if (data.status === "success") {
          setHistoryItems(data.items || []);
          setTotalPages(data.total_pages || 1);
          setTotalRecords(data.total || 0);
        }
      } catch (err) {
        console.error("Gagal mengambil riwayat scorecard:", err);
      } finally {
        setLoadingHistory(false);
      }
    },
    [selectedPair, historyMode, page]
  );

  useEffect(() => {
    fetchLatestScorecards(selectedPair);
    fetchScorecardHistory(selectedPair, historyMode, 1);
    setPage(1);
  }, [selectedPair, fetchLatestScorecards, fetchScorecardHistory]);

  const handleModeFilterChange = (newMode: string) => {
    setHistoryMode(newMode);
    setPage(1);
    fetchScorecardHistory(selectedPair, newMode, 1);
  };

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    setPage(newPage);
    fetchScorecardHistory(selectedPair, historyMode, newPage);
  };

  // Run On-Demand OOS Fit & Proper Evaluation
  const handleEvaluateOos = async (modeToEval: "normal" | "runner" | "all" = "all") => {
    setEvaluating(true);
    toast.info(
      `Memulai evaluasi Fit & Proper Test VectorBT untuk ${selectedPair} (${modeToEval.toUpperCase()})...`,
      "OOS Evaluator"
    );

    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/evaluate-oos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: selectedPair,
          mode: modeToEval,
          sample_candles: 50000,
        }),
      });
      const data = await res.json();

      if (data.status === "success") {
        toast.success(
          `Evaluasi OOS selesai (${data.sample_candles} candle diuji). Scorecard diperbarui.`,
          "Fit & Proper Selesai"
        );
        await fetchLatestScorecards(selectedPair);
        await fetchScorecardHistory(selectedPair, historyMode, 1);
        setPage(1);
      } else {
        toast.error(data.message || "Gagal menjalankan evaluasi OOS.", "Evaluasi Gagal");
      }
    } catch {
      toast.error("Gagal menghubungi endpoint evaluasi OOS.", "Error");
    } finally {
      setEvaluating(false);
    }
  };

  // Helper to extract metric values regardless of flat or nested structure
  const getMetricVal = (sc: ScorecardData | null, key: keyof ScorecardMetric, def = 0): number => {
    if (!sc) return def;
    if (sc.metrics && typeof sc.metrics[key] === "number") return sc.metrics[key];
    if (typeof (sc as any)[key] === "number") return (sc as any)[key];
    return def;
  };

  // Render a Single Scorecard Card (Normal or Runner)
  const renderScorecardCard = (mode: "normal" | "runner") => {
    const sc = latestScorecards[mode];
    const isNormal = mode === "normal";
    const modeTitle = isNormal ? "Normal Mode" : "Runner Mode";
    const targetRr = isNormal ? "RR 1:1.5" : "RR 1:5.0";

    const isEvaluated = sc !== null && (sc.passed !== undefined || sc.metrics !== undefined);
    const passed = sc?.passed === true;

    // Minimum targets per blueprint
    const targetWr = isNormal ? 52 : 28;
    const targetPf = isNormal ? 1.3 : 1.2;
    const targetSharpe = isNormal ? 0.8 : 0.5;
    const targetMaxDd = isNormal ? 20 : 35;
    const targetMinTrades = isNormal ? 30 : 20;

    const wr = getMetricVal(sc, "win_rate_pct");
    const pf = getMetricVal(sc, "profit_factor");
    const sharpe = getMetricVal(sc, "sharpe_ratio");
    const dd = getMetricVal(sc, "max_drawdown_pct");
    const trades = sc?.total_trades ?? sc?.metrics?.total_trades ?? 0;
    const ret = getMetricVal(sc, "total_return_pct");
    const th = sc?.threshold_used ? (sc.threshold_used * 100).toFixed(1) : null;
    const evalTime = sc?.evaluated_at || sc?.trained_at || "Belum ada riwayat";

    // Failure reasons list
    let failureReasons: string[] = [];
    if (sc?.reasons && Array.isArray(sc.reasons)) {
      failureReasons = sc.reasons;
    } else if (sc?.failure_reason) {
      failureReasons = sc.failure_reason.split(";").map((s) => s.trim()).filter(Boolean);
    }

    return (
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl flex flex-col justify-between relative overflow-hidden">
        {/* Glow accent */}
        <div
          className={`absolute top-0 right-0 w-32 h-32 rounded-full blur-3xl pointer-events-none -mr-10 -mt-10 ${
            !isEvaluated
              ? "bg-amber-500/10"
              : passed
              ? "bg-emerald-500/15"
              : "bg-rose-500/15"
          }`}
        />

        <div>
          {/* Card Header */}
          <div className="flex items-start justify-between gap-3 mb-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-white">{modeTitle}</span>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-white/5 text-white/60 border border-white/10">
                  {targetRr}
                </span>
              </div>
              <p className="text-[11px] text-white/50 flex items-center gap-1.5 mt-1">
                <Calendar size={12} className="text-brand-green" />
                <span>Evaluasi: {evalTime}</span>
              </p>
            </div>

            {/* Status Badge */}
            <div>
              {!isEvaluated ? (
                <span className="px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center gap-1.5">
                  <HelpCircle size={14} />
                  <span>BELUM DIEVALUASI</span>
                </span>
              ) : passed ? (
                <span className="px-3 py-1 rounded-full text-xs font-black bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center gap-1.5 shadow-sm shadow-emerald-500/20">
                  <CheckCircle2 size={14} className="text-emerald-400" />
                  <span>LULUS FIT &amp; PROPER</span>
                </span>
              ) : (
                <span className="px-3 py-1 rounded-full text-xs font-black bg-rose-500/20 text-rose-400 border border-rose-500/40 flex items-center gap-1.5 shadow-sm shadow-rose-500/20">
                  <XCircle size={14} className="text-rose-400" />
                  <span>GAGAL FIT &amp; PROPER</span>
                </span>
              )}
            </div>
          </div>

          {/* Failure reason banner if failed */}
          {isEvaluated && !passed && failureReasons.length > 0 && (
            <div className="mb-4 p-3 rounded-xl bg-rose-950/30 border border-rose-500/30 text-xs text-rose-300">
              <div className="font-bold flex items-center gap-1.5 mb-1 text-rose-400">
                <AlertTriangle size={14} />
                <span>Catatan Kriteria yang Belum Terpenuhi:</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-[11px] text-rose-200/80">
                {failureReasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 mb-4">
            {/* Win Rate */}
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5 flex flex-col">
              <div className="flex items-center justify-between text-[11px] text-white/50 mb-1">
                <span>Win Rate</span>
                <span className="text-[10px] text-white/30">Target: ≥{targetWr}%</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span
                  className={`text-lg font-black ${
                    !isEvaluated
                      ? "text-white/40"
                      : wr >= targetWr
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }`}
                >
                  {isEvaluated ? `${wr.toFixed(1)}%` : "-"}
                </span>
              </div>
            </div>

            {/* Profit Factor */}
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5 flex flex-col">
              <div className="flex items-center justify-between text-[11px] text-white/50 mb-1">
                <span>Profit Factor</span>
                <span className="text-[10px] text-white/30">Target: ≥{targetPf.toFixed(1)}</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span
                  className={`text-lg font-black ${
                    !isEvaluated
                      ? "text-white/40"
                      : pf >= targetPf
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }`}
                >
                  {isEvaluated ? pf.toFixed(2) : "-"}
                </span>
              </div>
            </div>

            {/* Sharpe Ratio */}
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5 flex flex-col">
              <div className="flex items-center justify-between text-[11px] text-white/50 mb-1">
                <span>Sharpe Ratio</span>
                <span className="text-[10px] text-white/30">Target: ≥{targetSharpe.toFixed(1)}</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span
                  className={`text-lg font-black ${
                    !isEvaluated
                      ? "text-white/40"
                      : sharpe >= targetSharpe
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }`}
                >
                  {isEvaluated ? sharpe.toFixed(2) : "-"}
                </span>
              </div>
            </div>

            {/* Max Drawdown */}
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5 flex flex-col">
              <div className="flex items-center justify-between text-[11px] text-white/50 mb-1">
                <span>Max Drawdown</span>
                <span className="text-[10px] text-white/30">Batas: ≤{targetMaxDd}%</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span
                  className={`text-lg font-black ${
                    !isEvaluated
                      ? "text-white/40"
                      : dd <= targetMaxDd
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }`}
                >
                  {isEvaluated ? `${dd.toFixed(1)}%` : "-"}
                </span>
              </div>
            </div>

            {/* Total Trades */}
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5 flex flex-col">
              <div className="flex items-center justify-between text-[11px] text-white/50 mb-1">
                <span>Total Trades</span>
                <span className="text-[10px] text-white/30">Min: ≥{targetMinTrades}</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span
                  className={`text-lg font-black ${
                    !isEvaluated
                      ? "text-white/40"
                      : trades >= targetMinTrades
                      ? "text-emerald-400"
                      : "text-amber-400"
                  }`}
                >
                  {isEvaluated ? trades : "-"}
                </span>
              </div>
            </div>

            {/* Total Return OOS */}
            <div className="p-3 rounded-xl bg-white/[0.03] border border-white/5 flex flex-col">
              <div className="flex items-center justify-between text-[11px] text-white/50 mb-1">
                <span>OOS Return</span>
                <span className="text-[10px] text-white/30">Akumulasi</span>
              </div>
              <div className="flex items-baseline gap-1.5">
                <span
                  className={`text-lg font-black ${
                    !isEvaluated
                      ? "text-white/40"
                      : ret >= 0
                      ? "text-emerald-400"
                      : "text-rose-400"
                  }`}
                >
                  {isEvaluated ? `${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%` : "-"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Card Footer: Metadata & Action */}
        <div className="pt-3 border-t border-white/5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-white/50">
          <div>
            <span>Threshold Aktif: </span>
            <span className="font-mono font-bold text-white/80">
              {th ? `${th}%` : "Default (54.0%)"}
            </span>
          </div>

          <button
            type="button"
            disabled={evaluating}
            onClick={() => handleEvaluateOos(mode)}
            className="px-3 py-1.5 rounded-lg text-xs font-bold bg-white/5 hover:bg-white/10 text-white/80 hover:text-white border border-white/10 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            {evaluating ? (
              <Loader2 size={12} className="animate-spin text-brand-green" />
            ) : (
              <Play size={12} className="text-brand-green" />
            )}
            <span>Tes {modeTitle}</span>
          </button>
        </div>
      </div>
    );
  };

  // Get active equity points for current tab
  const activeSc = latestScorecards[activeCurveTab];
  const activeCurvePoints = activeSc?.equity_curve || [];
  const isCurvePassed = activeSc?.passed !== false;

  return (
    <div className="flex flex-col gap-6 mb-8 shrink-0">
      {/* Section Header */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="text-brand-green w-5 h-5" />
            <h2 className="text-base sm:text-lg font-black text-white tracking-tight">
              Model Health Report ({selectedPair})
            </h2>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-brand-green/20 text-brand-green border border-brand-green/40">
              VectorBT OOS Engine
            </span>
          </div>
          <p className="text-xs text-white/50 mt-1 max-w-2xl">
            Verifikasi kelayakan finansial model AI pada data Out-Of-Sample (OOS). Gerbang Fit &amp; Proper Test memastikan hanya model dengan Win Rate, Sharpe, dan Drawdown teruji yang boleh beroperasi live.
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            disabled={evaluating || loadingLatest}
            onClick={() => handleEvaluateOos("all")}
            className="px-4 py-2.5 rounded-xl font-black text-xs bg-brand-green hover:bg-emerald-400 text-black shadow-lg shadow-brand-green/25 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
            title={`Jalankan simulasi VectorBT Fit & Proper Test pada data OOS ${selectedPair}`}
          >
            {evaluating ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Play size={14} className="fill-black" />
            )}
            <span>{evaluating ? "Mengevaluasi OOS..." : `Evaluasi Ulang OOS (${selectedPair})`}</span>
          </button>

          <button
            type="button"
            disabled={loadingLatest}
            onClick={() => {
              fetchLatestScorecards(selectedPair);
              fetchScorecardHistory(selectedPair, historyMode, page);
            }}
            className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-white/70 hover:text-white border border-white/10 transition-all cursor-pointer disabled:opacity-50"
            title="Refresh Scorecard Data"
          >
            <RotateCw size={15} className={loadingLatest ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Dual Cards: Normal Mode & Runner Mode */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {renderScorecardCard("normal")}
        {renderScorecardCard("runner")}
      </div>

      {/* Equity Curve Visualization Section */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/5 pb-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="text-brand-green w-4 h-4" />
            <h3 className="text-sm font-bold text-white">Visualisasi Kurva Ekuitas OOS (Out-of-Sample)</h3>
          </div>

          {/* Mode Switcher Tabs */}
          <div className="flex items-center gap-1.5 bg-black/40 p-1 rounded-xl border border-white/5">
            <button
              type="button"
              onClick={() => setActiveCurveTab("normal")}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeCurveTab === "normal"
                  ? "bg-brand-green text-black shadow-md shadow-brand-green/20"
                  : "text-white/60 hover:text-white"
              }`}
            >
              Normal Mode (1:1.5)
            </button>
            <button
              type="button"
              onClick={() => setActiveCurveTab("runner")}
              className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeCurveTab === "runner"
                  ? "bg-brand-green text-black shadow-md shadow-brand-green/20"
                  : "text-white/60 hover:text-white"
              }`}
            >
              Runner Mode (1:5.0)
            </button>
          </div>
        </div>

        {/* Lightweight Charts Component */}
        <EquityCurveChart
          data={activeCurvePoints}
          passed={isCurvePassed}
          symbol={selectedPair}
          mode={activeCurveTab}
        />
      </div>

      {/* Historical Scorecard Audit Log Table */}
      <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/5 pb-3">
          <div className="flex items-center gap-2">
            <History className="text-brand-green w-4 h-4" />
            <h3 className="text-sm font-bold text-white">Riwayat Evaluasi Scorecard ({selectedPair})</h3>
            <span className="text-[11px] text-white/40">({totalRecords} total entri)</span>
          </div>

          {/* Filter Mode Tabs */}
          <div className="flex items-center gap-1 bg-black/40 p-1 rounded-xl border border-white/5">
            {["all", "normal", "runner"].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => handleModeFilterChange(m)}
                className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer capitalize ${
                  historyMode === m
                    ? "bg-white/20 text-white shadow-sm"
                    : "text-white/50 hover:text-white"
                }`}
              >
                {m === "all" ? "Semua Mode" : m}
              </button>
            ))}
          </div>
        </div>

        {/* Table / List */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-white/10 text-white/40 uppercase tracking-wider text-[10px]">
                <th className="py-2.5 px-3">Waktu Evaluasi</th>
                <th className="py-2.5 px-3">Mode</th>
                <th className="py-2.5 px-3 text-right">Win Rate</th>
                <th className="py-2.5 px-3 text-right">Profit Factor</th>
                <th className="py-2.5 px-3 text-right">Sharpe</th>
                <th className="py-2.5 px-3 text-right">Max Drawdown</th>
                <th className="py-2.5 px-3 text-right">Return OOS</th>
                <th className="py-2.5 px-3 text-right">Trades</th>
                <th className="py-2.5 px-3 text-center">Status</th>
                <th className="py-2.5 px-3">Keterangan</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loadingHistory ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-white/40">
                    <Loader2 size={18} className="animate-spin inline mr-2 text-brand-green" />
                    Memuat riwayat scorecard...
                  </td>
                </tr>
              ) : historyItems.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-white/30">
                    Belum ada riwayat scorecard tersimpan untuk {selectedPair}.
                  </td>
                </tr>
              ) : (
                historyItems.map((item) => {
                  const isPassed = item.passed === true;
                  return (
                    <tr key={item.id ?? Math.random()} className="hover:bg-white/[0.02] transition-colors">
                      <td className="py-3 px-3 font-mono text-white/70 whitespace-nowrap">
                        {item.trained_at || item.evaluated_at || "-"}
                      </td>
                      <td className="py-3 px-3 whitespace-nowrap">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                            item.mode === "normal"
                              ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                              : "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                          }`}
                        >
                          {item.mode}
                        </span>
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-mono font-bold ${
                          (item.win_rate_pct ?? 0) >= (item.mode === "normal" ? 52 : 28)
                            ? "text-emerald-400"
                            : "text-rose-400"
                        }`}
                      >
                        {item.win_rate_pct !== undefined ? `${item.win_rate_pct.toFixed(1)}%` : "-"}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-mono font-bold ${
                          (item.profit_factor ?? 0) >= (item.mode === "normal" ? 1.3 : 1.2)
                            ? "text-emerald-400"
                            : "text-rose-400"
                        }`}
                      >
                        {item.profit_factor !== undefined ? item.profit_factor.toFixed(2) : "-"}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-mono font-bold ${
                          (item.sharpe_ratio ?? 0) >= (item.mode === "normal" ? 0.8 : 0.5)
                            ? "text-emerald-400"
                            : "text-rose-400"
                        }`}
                      >
                        {item.sharpe_ratio !== undefined ? item.sharpe_ratio.toFixed(2) : "-"}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-mono font-bold ${
                          (item.max_drawdown_pct ?? 0) <= (item.mode === "normal" ? 20 : 35)
                            ? "text-emerald-400"
                            : "text-rose-400"
                        }`}
                      >
                        {item.max_drawdown_pct !== undefined ? `${item.max_drawdown_pct.toFixed(1)}%` : "-"}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-mono font-bold ${
                          (item.total_return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {item.total_return_pct !== undefined
                          ? `${item.total_return_pct >= 0 ? "+" : ""}${item.total_return_pct.toFixed(1)}%`
                          : "-"}
                      </td>
                      <td className="py-3 px-3 text-right font-mono text-white/70">
                        {item.total_trades ?? "-"}
                      </td>
                      <td className="py-3 px-3 text-center whitespace-nowrap">
                        {isPassed ? (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 inline-flex items-center gap-1">
                            <CheckCircle2 size={11} /> LULUS
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-black bg-rose-500/20 text-rose-400 border border-rose-500/40 inline-flex items-center gap-1">
                            <XCircle size={11} /> GAGAL
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3 text-white/50 text-[11px] max-w-xs truncate" title={item.failure_reason || "Semua kriteria lolos"}>
                        {isPassed ? "Semua kriteria kelayakan terpenuhi" : item.failure_reason || "Tidak memenuhi threshold"}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between pt-2 border-t border-white/5 text-xs text-white/50">
            <span>
              Halaman {page} dari {totalPages}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={page <= 1 || loadingHistory}
                onClick={() => handlePageChange(page - 1)}
                className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/80 disabled:opacity-40 transition-all flex items-center gap-1 cursor-pointer"
              >
                <ChevronLeft size={14} />
                <span>Sebelumnya</span>
              </button>
              <button
                type="button"
                disabled={page >= totalPages || loadingHistory}
                onClick={() => handlePageChange(page + 1)}
                className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/80 disabled:opacity-40 transition-all flex items-center gap-1 cursor-pointer"
              >
                <span>Berikutnya</span>
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
