"use client";

import { useState, useEffect, useRef } from "react";
import { 
  Power, 
  Activity, 
  Cpu, 
  Clock, 
  Layers, 
  Terminal, 
  ShieldAlert, 
  ChevronUp, 
  ChevronDown, 
  TrendingUp, 
  TrendingDown, 
  Maximize2, 
  RefreshCw,
  Zap,
  Sparkles,
  ShieldCheck,
  Scissors,
  XCircle,
  Loader2
} from "lucide-react";
import dynamic from "next/dynamic";
import { getApiBaseUrl, getWsBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import NewsCountdown, { MacroEvent } from "@/components/NewsCountdown";

// Dynamically import TradingChart to avoid SSR issues with lightweight-charts canvas
const TradingChart = dynamic(() => import("@/components/TradingChart"), { ssr: false });

export default function Home() {
  const toast = useToast();
  const [isLive, setIsLive] = useState(false);
  const [selectedMode, setSelectedMode] = useState("auto");
  const [activeSymbol, setActiveSymbol] = useState<string>("XAUUSD");
  const [marketRegime, setMarketRegime] = useState<{ adx: number; regime: string }>({ adx: 0, regime: "DETECTING..." });
  const [onlineLearning, setOnlineLearning] = useState<{ enabled: boolean; last_retrain: string | null }>({ enabled: true, last_retrain: null });
  const [nextNews, setNextNews] = useState<MacroEvent | null>(null);
  const [openPositions, setOpenPositions] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<{ value: number; equity: number }>({ value: 10000, equity: 10000 });
  const [latestProbs, setLatestProbs] = useState<any>({
    normal_buy: 0.0,
    normal_sell: 0.0,
    runner_buy: 0.0,
    runner_sell: 0.0,
    normal: 0.5,
    runner: 0.5,
  });

  // Bottom Blotter Tabs & Collapse State
  const [blotterTab, setBlotterTab] = useState<"positions" | "telemetry" | "logs">("positions");
  const [isBlotterCollapsed, setIsBlotterCollapsed] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [actionLoadingTicket, setActionLoadingTicket] = useState<{ [ticket: number]: string }>({});
  const logsScrollRef = useRef<HTMLDivElement>(null);
  const wsLogsRef = useRef<WebSocket | null>(null);

  // Poll state every 3 seconds
  const fetchState = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/state`);
      if (!res.ok) return;
      const data = await res.json();
      setIsLive(data.is_live);
      if (data.active_symbol) setActiveSymbol(data.active_symbol);
      if (data.market_regime) setMarketRegime(data.market_regime);
      if (data.online_learning) setOnlineLearning(data.online_learning);
      if (data.next_high_impact_news !== undefined) setNextNews(data.next_high_impact_news);
      if (data.open_positions) setOpenPositions(data.open_positions);
      if (data.portfolio) setPortfolio(data.portfolio);
      if (data.latest_probabilities) setLatestProbs(data.latest_probabilities);
    } catch (err) {
      // Backend offline or polling delay
    }
  };

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 3000);
    return () => clearInterval(interval);
  }, []);

  // Connect to live WebSocket logs for the blotter
  useEffect(() => {
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    const connectLogsWs = () => {
      if (wsLogsRef.current && wsLogsRef.current.readyState === WebSocket.OPEN) return;
      const ws = new WebSocket(`${getWsBaseUrl()}/ws/logs`);
      wsLogsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "log") {
            setLogs((prev) => [...prev.slice(-150), msg.message]);
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        wsLogsRef.current = null;
        reconnectTimeout = setTimeout(connectLogsWs, 4000);
      };
    };

    connectLogsWs();
    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (wsLogsRef.current) {
        wsLogsRef.current.onclose = null;
        wsLogsRef.current.close();
      }
    };
  }, []);

  // Auto-scroll logs
  useEffect(() => {
    if (blotterTab === "logs" && logsScrollRef.current) {
      logsScrollRef.current.scrollTop = logsScrollRef.current.scrollHeight;
    }
  }, [logs, blotterTab]);

  const toggleLive = async () => {
    try {
      if (!isLive && selectedMode !== "auto") {
        await fetch(`${getApiBaseUrl()}/api/strategies/force_live`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: selectedMode.replace("force_", "") }),
        });
      }
      const res = await fetch(`${getApiBaseUrl()}/api/state/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ live: !isLive }),
      });
      const data = await res.json();
      setIsLive(data.is_live);
      if (data.is_live) {
        toast.success("AI Autonomous Trading Engine telah AKTIF.", "Live Execution Active");
      } else {
        toast.info("AI Autonomous Trading Engine telah DIHENTIKAN.", "Bot Paused");
      }
    } catch (err) {
      toast.error("Gagal mengubah status bot. Periksa koneksi backend.", "Error Toggle");
    }
  };

  const handlePositionAction = async (ticket: number, actionType: "break-even" | "partial-close" | "close", symbol: string) => {
    setActionLoadingTicket((prev) => ({ ...prev, [ticket]: actionType }));
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/positions/${actionType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket, symbol }),
      });
      const data = await res.json();
      if (data.status === "success") {
        if (actionType === "break-even") toast.success(`Tiket #${ticket} Stop Loss dipindah ke Break-Even (BE).`, "Protected");
        if (actionType === "partial-close") toast.success(`Tiket #${ticket} Partial Close 50% berhasil.`, "50% Closed");
        if (actionType === "close") toast.info(`Tiket #${ticket} berhasil ditutup penuh.`, "Trade Closed");
        fetchState();
      } else {
        toast.error(`Gagal mengeksekusi aksi pada tiket #${ticket}.`, "Gagal Eksekusi");
      }
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Koneksi Gagal");
    } finally {
      setActionLoadingTicket((prev) => {
        const next = { ...prev };
        delete next[ticket];
        return next;
      });
    }
  };

  const totalFloatingPnl = openPositions.reduce((acc, pos) => acc + (pos.profit || 0), 0);
  const balance = portfolio.value || 10000;
  const equity = portfolio.equity || balance;
  const currentDrawdown = balance > 0 ? Math.max(0, ((balance - equity) / balance) * 100) : 0;

  // Confidence calculations
  const normalBuyProb = Math.round((latestProbs.normal_buy || 0) * 100);
  const normalSellProb = Math.round((latestProbs.normal_sell || 0) * 100);
  const runnerBuyProb = Math.round((latestProbs.runner_buy || 0) * 100);
  const runnerSellProb = Math.round((latestProbs.runner_sell || 0) * 100);

  return (
    <div className="flex flex-col lg:flex-row h-full w-full overflow-hidden bg-[#070b0a] text-white select-none">
      
      {/* LEFT / CENTER: Main Interactive Chart & Bottom Blotter */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden border-r border-white/5">
        
        {/* Top Mini Header / Instrument Bar */}
        <div className="px-4 py-2 border-b border-white/10 bg-black/40 flex items-center justify-between shrink-0 gap-3">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="font-black text-sm tracking-wider text-white font-mono">{activeSymbol}</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-white/10 text-white/70 border border-white/10">
                Gold Spot
              </span>
            </div>
            <div className="h-3.5 w-px bg-white/10 hidden sm:block" />
            <div className="hidden sm:flex items-center gap-2 text-xs font-mono tabular-nums">
              <span className="text-white/40">Equity:</span>
              <span className="font-bold text-white">${equity.toFixed(2)}</span>
            </div>
            <div className="h-3.5 w-px bg-white/10 hidden sm:block" />
            <div className="hidden sm:flex items-center gap-2 text-xs font-mono tabular-nums">
              <span className="text-white/40">Floating:</span>
              <span className={`font-bold ${totalFloatingPnl >= 0 ? "text-brand-green" : "text-brand-red"}`}>
                {totalFloatingPnl >= 0 ? "+" : ""}${totalFloatingPnl.toFixed(2)}
              </span>
            </div>
          </div>

          {/* Header Status Indicator */}
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isLive ? "bg-emerald-400 animate-pulse" : "bg-amber-400"}`} />
            <span className="text-xs font-mono font-bold tracking-wider text-white/80">
              {isLive ? "AUTONOMOUS LIVE" : "STANDBY (STREAMING)"}
            </span>
          </div>
        </div>

        {/* Central Candlestick Chart Viewport */}
        <div className="flex-1 relative w-full min-h-[300px] bg-black/30">
          <TradingChart isLive={isLive} symbol={activeSymbol} positions={openPositions} />
        </div>

        {/* BOTTOM: Docked Multi-Tab Blotter */}
        <div className={`border-t border-white/10 bg-[#090e0c] flex flex-col shrink-0 transition-all duration-300 ${
          isBlotterCollapsed ? "h-10" : "h-44 sm:h-52"
        }`}>
          {/* Blotter Header & Tabs */}
          <div className="px-3 py-1.5 border-b border-white/10 flex items-center justify-between bg-black/40 text-xs shrink-0">
            <div className="flex items-center gap-1.5 sm:gap-2">
              <button
                onClick={() => { setBlotterTab("positions"); setIsBlotterCollapsed(false); }}
                className={`px-3 py-1 rounded-lg font-bold text-xs flex items-center gap-1.5 transition-all ${
                  blotterTab === "positions" && !isBlotterCollapsed
                    ? "bg-brand-green/20 text-brand-green border border-brand-green/40"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <Layers size={13} />
                <span>Open Positions</span>
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-white/10 text-white font-mono tabular-nums">
                  {openPositions.length}
                </span>
              </button>

              <button
                onClick={() => { setBlotterTab("telemetry"); setIsBlotterCollapsed(false); }}
                className={`px-3 py-1 rounded-lg font-bold text-xs flex items-center gap-1.5 transition-all ${
                  blotterTab === "telemetry" && !isBlotterCollapsed
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <Activity size={13} />
                <span>Account Telemetry</span>
              </button>

              <button
                onClick={() => { setBlotterTab("logs"); setIsBlotterCollapsed(false); }}
                className={`px-3 py-1 rounded-lg font-bold text-xs flex items-center gap-1.5 transition-all ${
                  blotterTab === "logs" && !isBlotterCollapsed
                    ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <Terminal size={13} />
                <span>Live Event Feed</span>
              </button>
            </div>

            {/* Collapse / Expand Toggle */}
            <button
              onClick={() => setIsBlotterCollapsed(!isBlotterCollapsed)}
              className="p-1 rounded hover:bg-white/10 text-white/50 hover:text-white transition-colors cursor-pointer"
              title={isBlotterCollapsed ? "Expand Blotter" : "Collapse Blotter"}
            >
              {isBlotterCollapsed ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          </div>

          {/* Blotter Content Area */}
          {!isBlotterCollapsed && (
            <div className="flex-1 overflow-hidden relative">
              {/* Tab 1: Open Positions Blotter */}
              {blotterTab === "positions" && (
                <div className="w-full h-full overflow-y-auto custom-scrollbar">
                  {openPositions.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-white/30 text-xs font-mono">
                      Belum ada transaksi aktif yang terbuka di server broker MT5.
                    </div>
                  ) : (
                    <table className="w-full text-left text-xs font-mono tabular-nums">
                      <thead className="sticky top-0 bg-[#070b0a] border-b border-white/10 text-white/40 uppercase text-[10px] tracking-wider z-10">
                        <tr>
                          <th className="py-2.5 px-3">Ticket</th>
                          <th className="py-2.5 px-3">Type</th>
                          <th className="py-2.5 px-3">Vol</th>
                          <th className="py-2.5 px-3">Open</th>
                          <th className="py-2.5 px-3">Current</th>
                          <th className="py-2.5 px-3">SL / TP</th>
                          <th className="py-2.5 px-3 text-right">Profit</th>
                          <th className="py-2.5 px-3 text-center">Blotter Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5">
                        {openPositions.map((pos) => {
                          const isBuy = pos.type === "BUY";
                          const isProfit = pos.profit >= 0;
                          const isLoading = !!actionLoadingTicket[pos.ticket];

                          return (
                            <tr key={pos.ticket} className="hover:bg-white/[0.02] transition-colors">
                              <td className="py-2 px-3 text-white/40">#{pos.ticket}</td>
                              <td className="py-2 px-3">
                                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                  isBuy ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                                }`}>
                                  {pos.type}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-white/80">{pos.volume.toFixed(2)}</td>
                              <td className="py-2 px-3 text-white/80">{pos.open_price.toFixed(2)}</td>
                              <td className="py-2 px-3 font-semibold text-white">{pos.current_price.toFixed(2)}</td>
                              <td className="py-2 px-3 text-white/60">
                                {pos.sl ? pos.sl.toFixed(1) : "-"} / {pos.tp ? pos.tp.toFixed(1) : "-"}
                              </td>
                              <td className={`py-2 px-3 text-right font-bold text-sm ${
                                isProfit ? "text-brand-green" : "text-brand-red"
                              }`}>
                                {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
                              </td>
                              <td className="py-2 px-3">
                                <div className="flex items-center justify-center gap-1">
                                  <button
                                    onClick={() => handlePositionAction(pos.ticket, "break-even", pos.symbol)}
                                    disabled={isLoading}
                                    title="Geser SL ke Break-Even"
                                    className="px-2 py-0.5 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold flex items-center gap-0.5 transition-all disabled:opacity-40"
                                  >
                                    <ShieldCheck size={11} /> BE
                                  </button>
                                  <button
                                    onClick={() => handlePositionAction(pos.ticket, "partial-close", pos.symbol)}
                                    disabled={isLoading}
                                    title="Tutup 50% Volume"
                                    className="px-2 py-0.5 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-bold flex items-center gap-0.5 transition-all disabled:opacity-40"
                                  >
                                    <Scissors size={11} /> 50%
                                  </button>
                                  <button
                                    onClick={() => handlePositionAction(pos.ticket, "close", pos.symbol)}
                                    disabled={isLoading}
                                    title="Tutup Posisi Penuh"
                                    className="px-2 py-0.5 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-[10px] font-bold flex items-center gap-0.5 transition-all disabled:opacity-40"
                                  >
                                    <XCircle size={11} /> Close
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              {/* Tab 2: Account Telemetry */}
              {blotterTab === "telemetry" && (
                <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-3 h-full overflow-y-auto custom-scrollbar font-mono tabular-nums">
                  <div className="bg-white/5 border border-white/5 rounded-xl p-3 flex flex-col justify-between">
                    <span className="text-[10px] uppercase font-bold text-white/40">Balance</span>
                    <span className="text-lg font-black text-white">${balance.toFixed(2)}</span>
                    <span className="text-[10px] text-white/40">Modal riil broker</span>
                  </div>

                  <div className="bg-white/5 border border-white/5 rounded-xl p-3 flex flex-col justify-between">
                    <span className="text-[10px] uppercase font-bold text-white/40">Equity</span>
                    <span className="text-lg font-black text-white">${equity.toFixed(2)}</span>
                    <span className="text-[10px] text-white/40">Nilai ekuitas berjalan</span>
                  </div>

                  <div className="bg-white/5 border border-white/5 rounded-xl p-3 flex flex-col justify-between">
                    <span className="text-[10px] uppercase font-bold text-white/40">Floating PnL</span>
                    <span className={`text-lg font-black ${totalFloatingPnl >= 0 ? "text-brand-green" : "text-brand-red"}`}>
                      {totalFloatingPnl >= 0 ? "+" : ""}${totalFloatingPnl.toFixed(2)}
                    </span>
                    <span className="text-[10px] text-white/40">{openPositions.length} posisi terbuka</span>
                  </div>

                  <div className="bg-white/5 border border-white/5 rounded-xl p-3 flex flex-col justify-between">
                    <span className="text-[10px] uppercase font-bold text-white/40">Max Drawdown Sekring</span>
                    <span className="text-lg font-black text-emerald-400">
                      {currentDrawdown.toFixed(1)}% <span className="text-xs text-white/40">/ 30.0%</span>
                    </span>
                    <span className="text-[10px] text-white/40">Circuit breaker batas rugi</span>
                  </div>
                </div>
              )}

              {/* Tab 3: Live Event Terminal Log Feed */}
              {blotterTab === "logs" && (
                <div 
                  ref={logsScrollRef}
                  className="w-full h-full p-3 font-mono text-[11px] overflow-y-auto custom-scrollbar bg-black/60 flex flex-col gap-1"
                >
                  {logs.length === 0 ? (
                    <span className="text-white/30 italic">Menunggu streaming log dari agen trading...</span>
                  ) : (
                    logs.map((log, i) => {
                      const isWarning = log.includes("WARNING");
                      const isError = log.includes("ERROR");
                      let colorClass = "text-white/70";
                      if (isWarning) colorClass = "text-yellow-400 font-bold";
                      if (isError) colorClass = "text-rose-400 font-bold";
                      return (
                        <div key={i} className={`${colorClass} hover:bg-white/5 px-2 py-0.5 rounded break-all`}>
                          {log}
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          )}
        </div>

      </div>

      {/* RIGHT: Docked Quant Cockpit HUD */}
      <div className="w-full lg:w-80 shrink-0 flex flex-col gap-3 p-3 overflow-y-auto custom-scrollbar bg-[#090e0c]/90">
        
        {/* Module 1: AI Execution Master Control */}
        <div className="glass-panel p-4 flex flex-col shrink-0 gap-3 relative">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-1.5">
              <Zap size={14} className="text-amber-400" /> AI Execution
            </span>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
              isLive 
                ? "bg-brand-green/20 text-brand-green border border-brand-green/40 animate-pulse" 
                : "bg-white/10 text-white/40 border border-white/5"
            }`}>
              {isLive ? "LIVE ACTIVE" : "PAUSED"}
            </span>
          </div>

          <div className="space-y-2">
            {!isLive && (
              <select 
                value={selectedMode} 
                onChange={(e) => setSelectedMode(e.target.value)}
                className="w-full bg-black/60 border border-white/10 text-white text-xs rounded-xl p-2.5 focus:ring-1 focus:ring-brand-green outline-none font-medium cursor-pointer"
              >
                <option value="auto">Auto (Strict OOS Validation)</option>
                <option value="force_normal">Forced Live: Normal Mode</option>
                <option value="force_runner">Forced Live: Runner Mode</option>
              </select>
            )}

            <button 
              onClick={toggleLive}
              className={`flex items-center justify-center gap-2.5 py-3 px-4 rounded-xl transition-all duration-300 w-full font-black text-sm sm:text-base tracking-widest cursor-pointer shadow-lg ${
                isLive 
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50 hover:bg-rose-500/30' 
                  : 'bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold shadow-emerald-500/20'
              }`}
            >
              <Power size={18} className={isLive ? 'animate-pulse' : ''} />
              <span>{isLive ? 'STOP BOT' : 'START BOT'}</span>
            </button>
          </div>

          <p className="text-[10px] text-white/40 font-mono text-center">
            {isLive ? 'Mesin otonom M1 memantau order...' : 'Algoritma siap diaktifkan'}
          </p>
        </div>

        {/* Module 2: AI Probabilities Radar (Dual-Target LightGBM) */}
        <div className="glass-panel p-4 flex flex-col shrink-0 gap-3 font-mono tabular-nums">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-1.5 font-sans">
              <Sparkles size={14} className="text-cyan-400" /> AI Confidence
            </span>
            <span className="text-[10px] text-white/40">Dual-Target</span>
          </div>

          {/* Normal Mode (Scalp) */}
          <div className="bg-black/30 p-2.5 rounded-xl border border-white/5 flex flex-col gap-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="font-sans font-bold text-white/80">Normal Scalp</span>
              <span className="text-cyan-300 font-bold">{Math.max(normalBuyProb, normalSellProb)}%</span>
            </div>
            <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden flex">
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
            <div className="flex justify-between text-[10px] text-white/40">
              <span>B: {normalBuyProb}%</span>
              <span>S: {normalSellProb}%</span>
            </div>
          </div>

          {/* Runner Mode (Trend) */}
          <div className="bg-black/30 p-2.5 rounded-xl border border-white/5 flex flex-col gap-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="font-sans font-bold text-white/80">Runner Trend</span>
              <span className="text-purple-300 font-bold">{Math.max(runnerBuyProb, runnerSellProb)}%</span>
            </div>
            <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden flex">
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
            <div className="flex justify-between text-[10px] text-white/40">
              <span>B: {runnerBuyProb}%</span>
              <span>S: {runnerSellProb}%</span>
            </div>
          </div>

          {/* Market Regime */}
          <div className="pt-2 border-t border-white/5 flex items-center justify-between text-xs">
            <span className="font-sans text-white/50">Regime:</span>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
              marketRegime.regime === "TRENDING" ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30" :
              marketRegime.regime === "RANGING/CHOPPY" ? "bg-amber-500/20 text-amber-300 border border-amber-500/30" :
              "bg-blue-500/20 text-blue-300 border border-blue-500/30"
            }`}>
              {marketRegime.regime} (ADX {marketRegime.adx.toFixed(1)})
            </span>
          </div>

          <div className="flex items-center justify-between text-[10px] text-white/40">
            <span className="font-sans">Micro-Retrain:</span>
            <span>{onlineLearning.last_retrain ? onlineLearning.last_retrain.substring(11, 16) : "Ready"}</span>
          </div>
        </div>

        {/* Module 3: Macro News Radar */}
        <NewsCountdown initialEvent={nextNews} />

      </div>

    </div>
  );
}
