"use client";

import { useState, useEffect } from "react";
import { BookOpen, Cpu, ShieldAlert, Zap, TrendingUp, Crosshair, RefreshCw } from "lucide-react";

interface PerformanceStats {
  total_trades: number;
  win_rate: number;
  total_profit: number;
  wins: number;
  losses: number;
}

interface PerformanceSummary {
  normal: PerformanceStats;
  runner: PerformanceStats;
  all: PerformanceStats;
}

export default function JournalPage() {
  const [data, setData] = useState<{
    journal: any[];
    trade_logs: any[];
    open_positions: any[];
    performance?: PerformanceSummary;
  }>({
    journal: [],
    trade_logs: [],
    open_positions: [],
    performance: {
      normal: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 },
      runner: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 },
      all: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 }
    }
  });

  const [loading, setLoading] = useState(true);
  const [selectedFilter, setSelectedFilter] = useState<"ALL" | "NORMAL" | "RUNNER">("ALL");

  const fetchJournal = () => {
    setLoading(true);
    fetch("http://localhost:8000/api/journal?limit=200")
      .then(res => res.json())
      .then(resData => {
        if (resData.status === "success") {
          setData({
            journal: resData.journal || [],
            trade_logs: resData.trade_logs || [],
            open_positions: resData.open_positions || [],
            performance: resData.performance || {
              normal: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 },
              runner: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 },
              all: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 }
            }
          });
        }
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load journal", err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchJournal();
    // Auto-refresh setiap 20 detik
    const interval = setInterval(fetchJournal, 20000);
    return () => clearInterval(interval);
  }, []);

  const perf = data.performance || {
    normal: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 },
    runner: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 },
    all: { total_trades: 0, win_rate: 0, total_profit: 0, wins: 0, losses: 0 }
  };

  const isRunnerMode = (mode: string | undefined | null) => {
    return (mode || "").toUpperCase().includes("RUNNER");
  };

  const normalTradesCount = data.trade_logs.filter((t: any) => !isRunnerMode(t.mode)).length;
  const runnerTradesCount = data.trade_logs.filter((t: any) => isRunnerMode(t.mode)).length;

  const filteredTrades = data.trade_logs.filter((trade: any) => {
    if (selectedFilter === "ALL") return true;
    const isRunner = isRunnerMode(trade.mode);
    if (selectedFilter === "RUNNER") return isRunner;
    if (selectedFilter === "NORMAL") return !isRunner;
    return true;
  });

  return (
    <div className="p-6 h-full flex flex-col overflow-y-auto">
      {/* Header */}
      <div className="mb-6 shrink-0 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-white tracking-widest flex items-center gap-3">
            <BookOpen className="text-brand-green" /> TRADE JOURNAL &amp; XAI
          </h1>
          <p className="text-white/50 mt-1">
            Pencatatan terpisah performa riil: <strong className="text-cyan-400">Normal (Hit &amp; Run)</strong> vs <strong className="text-purple-400">Runner Mode</strong>.
          </p>
        </div>
        <button
          onClick={fetchJournal}
          disabled={loading}
          className="bg-white/5 hover:bg-white/10 text-white/70 border border-white/10 px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2 transition-all disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* KPI Cards: Normal vs Runner vs Total */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8 shrink-0">
        {/* Card 1: Normal Mode */}
        <div className="glass-panel p-5 border-l-4 border-l-cyan-400 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Zap className="text-cyan-400" size={18} />
              <span className="text-xs font-black uppercase tracking-wider text-cyan-400">Normal Mode (RR 1:2)</span>
            </div>
            <span className="text-[10px] font-mono text-white/40 bg-white/5 px-2 py-0.5 rounded">Hit &amp; Run</span>
          </div>
          <div className="flex items-baseline justify-between mb-2">
            <span className={`text-2xl font-black ${perf.normal.total_profit >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
              {perf.normal.total_profit >= 0 ? '+' : ''}${perf.normal.total_profit.toFixed(2)}
            </span>
            <span className="text-xs font-bold text-white/70">
              Win Rate: <strong className={perf.normal.win_rate >= 50 ? 'text-brand-green' : 'text-orange-400'}>{perf.normal.win_rate}%</strong>
            </span>
          </div>
          <div className="text-[11px] text-white/40 flex justify-between pt-2 border-t border-white/5">
            <span>Trades: <strong>{perf.normal.total_trades}</strong></span>
            <span>Menang: <strong className="text-brand-green">{perf.normal.wins}</strong> / Kalah: <strong className="text-brand-red">{perf.normal.losses}</strong></span>
          </div>
        </div>

        {/* Card 2: Runner Mode */}
        <div className="glass-panel p-5 border-l-4 border-l-purple-500 flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Crosshair className="text-purple-400" size={18} />
              <span className="text-xs font-black uppercase tracking-wider text-purple-400">Runner Mode (RR 1:5)</span>
            </div>
            <span className="text-[10px] font-mono text-white/40 bg-white/5 px-2 py-0.5 rounded">Trend Ride</span>
          </div>
          <div className="flex items-baseline justify-between mb-2">
            <span className={`text-2xl font-black ${perf.runner.total_profit >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
              {perf.runner.total_profit >= 0 ? '+' : ''}${perf.runner.total_profit.toFixed(2)}
            </span>
            <span className="text-xs font-bold text-white/70">
              Win Rate: <strong className={perf.runner.win_rate >= 50 ? 'text-brand-green' : 'text-orange-400'}>{perf.runner.win_rate}%</strong>
            </span>
          </div>
          <div className="text-[11px] text-white/40 flex justify-between pt-2 border-t border-white/5">
            <span>Trades: <strong>{perf.runner.total_trades}</strong></span>
            <span>Menang: <strong className="text-brand-green">{perf.runner.wins}</strong> / Kalah: <strong className="text-brand-red">{perf.runner.losses}</strong></span>
          </div>
        </div>

        {/* Card 3: Overall Portfolio */}
        <div className="glass-panel p-5 border-l-4 border-l-brand-green flex flex-col justify-between">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <TrendingUp className="text-brand-green" size={18} />
              <span className="text-xs font-black uppercase tracking-wider text-brand-green">Total Realized PnL</span>
            </div>
            <span className="text-[10px] font-mono text-white/40 bg-white/5 px-2 py-0.5 rounded">Combined</span>
          </div>
          <div className="flex items-baseline justify-between mb-2">
            <span className={`text-2xl font-black ${perf.all.total_profit >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
              {perf.all.total_profit >= 0 ? '+' : ''}${perf.all.total_profit.toFixed(2)}
            </span>
            <span className="text-xs font-bold text-white/70">
              Win Rate: <strong className={perf.all.win_rate >= 50 ? 'text-brand-green' : 'text-orange-400'}>{perf.all.win_rate}%</strong>
            </span>
          </div>
          <div className="text-[11px] text-white/40 flex justify-between pt-2 border-t border-white/5">
            <span>Total Trades: <strong>{perf.all.total_trades}</strong></span>
            <span>Menang: <strong className="text-brand-green">{perf.all.wins}</strong> / Kalah: <strong className="text-brand-red">{perf.all.losses}</strong></span>
          </div>
        </div>
      </div>

      {/* Main Content Grid: XAI Logs + Trade History Table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8 flex-1 min-h-0">
        
        {/* Left Column: XAI Black Box Logs */}
        <div className="glass-panel p-6 flex flex-col gap-4 overflow-hidden">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <Cpu className="text-brand-blue" /> Riwayat Aksi Black Box (XAI)
            </h2>
            <span className="text-xs text-white/40">{data.journal.length} event</span>
          </div>
          <p className="text-sm text-white/50">Inspeksi alasan di balik setiap keputusan eksekusi AI (Top Feature Contributions).</p>
          
          <div className="flex flex-col gap-4 overflow-y-auto pr-2 flex-1">
            {loading && data.journal.length === 0 ? (
               <div className="text-white/30 text-sm">Loading logs...</div>
            ) : data.journal.length === 0 ? (
               <div className="text-center p-8 border border-dashed border-white/10 rounded-xl text-white/30 text-sm">
                  Belum ada event transaksi riil.
               </div>
            ) : (
               data.journal.map((log: any, i: number) => (
                 <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-4">
                   <div className="flex justify-between items-start mb-2">
                     <div>
                       <span className={`text-xs font-bold px-2 py-1 rounded-full ${log.event_type === 'ENTRY' ? 'bg-brand-blue/20 text-brand-blue' : log.event_type === 'SL_MODIFY' ? 'bg-yellow-500/20 text-yellow-500' : 'bg-brand-red/20 text-brand-red'}`}>
                         {log.event_type}
                       </span>
                       <span className="text-xs text-white/50 ml-2">Ticket: #{log.tiket}</span>
                     </div>
                     <div className="text-xs text-white/40">{new Date(log.timestamp).toLocaleString()}</div>
                   </div>
                   
                   <div className="text-lg font-bold text-white my-2">@ {log.harga.toFixed(2)}</div>
                   
                   <div className="mt-4 p-3 bg-black/40 rounded border border-white/5">
                     <div className="text-xs font-bold text-white/70 mb-1 flex items-center gap-1">
                       <ShieldAlert size={12} /> Alasan AI (Feature Weights)
                     </div>
                     <div className="text-sm text-brand-green/90 whitespace-pre-wrap font-mono">
                       {log.alasan}
                     </div>
                   </div>
                 </div>
               ))
            )}
          </div>
        </div>

        {/* Right Column: Trade Logs (PnL) */}
        <div className="glass-panel p-6 flex flex-col gap-4 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <BookOpen className="text-brand-green" /> Riwayat Transaksi (PnL)
            </h2>

            {/* Filter Tabs */}
            <div className="flex items-center gap-1 p-1 bg-white/5 rounded-xl border border-white/10 text-xs">
              <button
                onClick={() => setSelectedFilter("ALL")}
                className={`px-3 py-1 rounded-lg font-bold transition-all ${
                  selectedFilter === "ALL" ? "bg-white/20 text-white" : "text-white/40 hover:text-white"
                }`}
              >
                Semua ({data.trade_logs.length})
              </button>
              <button
                onClick={() => setSelectedFilter("NORMAL")}
                className={`px-3 py-1 rounded-lg font-bold transition-all ${
                  selectedFilter === "NORMAL" ? "bg-cyan-500/30 text-cyan-300" : "text-white/40 hover:text-white"
                }`}
              >
                ⚡ Normal ({normalTradesCount})
              </button>
              <button
                onClick={() => setSelectedFilter("RUNNER")}
                className={`px-3 py-1 rounded-lg font-bold transition-all ${
                  selectedFilter === "RUNNER" ? "bg-purple-600/40 text-purple-300" : "text-white/40 hover:text-white"
                }`}
              >
                🏹 Runner ({runnerTradesCount})
              </button>
            </div>
          </div>

          {/* Active Open Positions from MT5 */}
          {data.open_positions && data.open_positions.length > 0 && (
            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3 shrink-0">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold text-emerald-400 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  Posisi Terbuka MT5 (Floating)
                </span>
                <span className="text-[11px] font-mono text-emerald-300 font-bold">
                  {data.open_positions.length} Posisi Aktif
                </span>
              </div>
              <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                {data.open_positions.map((pos: any, idx: number) => (
                  <div key={idx} className="flex items-center justify-between text-xs bg-black/40 p-2 rounded-lg border border-white/5">
                    <div className="flex items-center gap-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-black ${pos.action === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                        {pos.action}
                      </span>
                      <span className="font-mono text-white/70">#{pos.ticket}</span>
                      <span className="text-white/40">{pos.volume} lot @ {pos.price}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-white/40 text-[10px]">Now: {pos.current_price}</span>
                      <span className={`font-mono font-bold ${pos.profit >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                        {pos.profit >= 0 ? '+' : ''}${pos.profit.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <p className="text-sm text-white/50">Daftar posisi tertutup dengan atribusi mode dan profit riil.</p>
          
          <div className="flex-1 overflow-y-auto border border-white/5 rounded-xl">
            <table className="w-full text-left">
              <thead className="sticky top-0 bg-black/80 backdrop-blur border-b border-white/10 text-white/50 text-xs uppercase tracking-wider">
                <tr>
                  <th className="p-3 font-medium">Ticket</th>
                  <th className="p-3 font-medium">Setup ID</th>
                  <th className="p-3 font-medium">Mode</th>
                  <th className="p-3 font-medium">Type</th>
                  <th className="p-3 font-medium">Volume</th>
                  <th className="p-3 font-medium text-right">Profit</th>
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-white/5">
                {loading && data.trade_logs.length === 0 ? (
                  <tr><td colSpan={6} className="p-4 text-white/30 text-sm">Loading...</td></tr>
                ) : filteredTrades.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-8 text-center text-white/30">
                      Belum ada history trading untuk filter ini.
                    </td>
                  </tr>
                ) : (
                  filteredTrades.map((trade: any, i: number) => {
                    const isRunner = isRunnerMode(trade.mode);
                    return (
                      <tr key={i} className="hover:bg-white/5 transition-colors">
                        <td className="p-3 font-bold text-white/70">
                          #{trade.ticket || trade.id}
                        </td>
                        <td className="p-3 text-[11px] font-mono text-white/40 truncate max-w-[140px]" title={trade.setup_id || "-"}>
                          {trade.setup_id || "-"}
                        </td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-black tracking-wide border ${
                            isRunner
                              ? "bg-purple-500/20 text-purple-400 border-purple-500/40"
                              : "bg-cyan-500/20 text-cyan-400 border-cyan-500/40"
                          }`}>
                            {isRunner ? "RUNNER" : "NORMAL"}
                          </span>
                        </td>
                        <td className={`p-3 font-bold ${trade.action === 'BUY' ? 'text-brand-green' : 'text-brand-red'}`}>
                          {trade.action}
                        </td>
                        <td className="p-3 text-white/70">{trade.volume ? trade.volume.toFixed(2) : '-'}</td>
                        <td className={`p-3 font-bold text-right ${trade.profit >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                          {trade.profit >= 0 ? '+' : ''}${trade.profit ? trade.profit.toFixed(2) : '0.00'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </div>
  );
}

