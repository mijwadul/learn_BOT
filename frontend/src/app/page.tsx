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
  TrendingUp, 
  TrendingDown, 
  RefreshCw,
  Zap,
  Sparkles,
  ShieldCheck,
  Scissors,
  XCircle,
  Plus,
  Trash2,
  Database,
  BarChart3,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Info,
  Brain
} from "lucide-react";
import { getApiBaseUrl, getWsBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import NewsCountdown, { MacroEvent } from "@/components/NewsCountdown";

export default function Home() {
  const toast = useToast();
  const [isLive, setIsLive] = useState(false);
  const [selectedMode, setSelectedMode] = useState("auto");
  const [activeSymbol, setActiveSymbol] = useState<string>("XAUUSD");
  const [pairs, setPairs] = useState<any[]>([{ symbol: "XAUUSD", is_active: true }]);
  const [showAddPairModal, setShowAddPairModal] = useState(false);
  const [newPairInput, setNewPairInput] = useState("");
  const [isAddingPair, setIsAddingPair] = useState(false);

  // States for Strategy Otak (Brain) activation
  const [isNormalActive, setIsNormalActive] = useState(false);
  const [isRunnerActive, setIsRunnerActive] = useState(false);
  const [allBrainsActive, setAllBrainsActive] = useState(false);
  const [isTogglingBrain, setIsTogglingBrain] = useState(false);

  const [marketRegime, setMarketRegime] = useState<{ adx: number; regime: string }>({ adx: 0, regime: "DETECTING..." });
  const [onlineLearning, setOnlineLearning] = useState<{ enabled: boolean; last_retrain: string | null }>({ enabled: true, last_retrain: null });
  const [isMicroRetraining, setIsMicroRetraining] = useState(false);
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

  // Bottom Blotter Tabs & Logs State
  const [blotterTab, setBlotterTab] = useState<"positions" | "telemetry" | "logs" | "pairs">("positions");
  const [logs, setLogs] = useState<string[]>([]);
  const [actionLoadingTicket, setActionLoadingTicket] = useState<{ [ticket: number]: string }>({});
  const logsScrollRef = useRef<HTMLDivElement>(null);
  const wsLogsRef = useRef<WebSocket | null>(null);

  const fetchPairs = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/pairs`);
      const data = await res.json();
      if (data.status === "success" && data.pairs) {
        setPairs(data.pairs);
      }
    } catch {
      // backend offline
    }
  };

  const handleTogglePair = async (symbol: string, currentActive: boolean) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/pairs/toggle`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, active: !currentActive }),
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.info(data.message, "Multi-Pair Manager");
        fetchPairs();
      }
    } catch {
      toast.error("Gagal mengubah status aktif pair.", "Error");
    }
  };

  const handleAddPair = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanSym = newPairInput.trim().toUpperCase();
    if (!cleanSym) return;
    setIsAddingPair(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/pairs/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: cleanSym }),
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.success(data.message, "Pair Ditambahkan");
        setNewPairInput("");
        setShowAddPairModal(false);
        setActiveSymbol(cleanSym);
        fetchPairs();
      } else {
        toast.error(data.message || "Gagal menambahkan pair.", "Registrasi Pair");
      }
    } catch {
      toast.error("Gagal menghubungi backend.", "Koneksi Error");
    } finally {
      setIsAddingPair(false);
    }
  };

  const handleRemovePair = async (symbol: string) => {
    if (symbol === "XAUUSD") return;
    if (!confirm(`Hapus pair ${symbol} dari pemantauan bot?`)) return;
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/pairs/remove`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol }),
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.info(data.message, "Pair Dihapus");
        if (activeSymbol === symbol) setActiveSymbol("XAUUSD");
        fetchPairs();
      } else {
        toast.error(data.message, "Gagal Hapus");
      }
    } catch {
      toast.error("Gagal menghapus pair.", "Error");
    }
  };

  const handleTriggerMicroRetrain = async () => {
    setIsMicroRetraining(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/strategies/micro-train`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "all" }),
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.success("Online Micro-Retrain telah dipicu di background.", "AI Learning Engine");
      }
    } catch {
      toast.error("Gagal memicu micro-retrain.", "Error");
    } finally {
      setTimeout(() => setIsMicroRetraining(false), 3000);
    }
  };

  const handleToggleBrain = async (mode: "normal" | "runner" | "all", active: boolean) => {
    setIsTogglingBrain(true);
    try {
      const endpoint = mode === "all" ? "/api/strategies/toggle-all-brains" : "/api/strategies/toggle-brain";
      const body = mode === "all" ? { active, symbol: activeSymbol } : { mode, active, symbol: activeSymbol };
      const res = await fetch(`${getApiBaseUrl()}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.success(data.message, "Saklar Otak AI");
        if (data.is_normal_active !== undefined) setIsNormalActive(data.is_normal_active);
        if (data.is_runner_active !== undefined) setIsRunnerActive(data.is_runner_active);
        if (data.all_active !== undefined) setAllBrainsActive(data.all_active);
        fetchState();
      } else {
        toast.warning(data.message || "Gagal mengubah status otak.", "Perhatian");
      }
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Error");
    } finally {
      setIsTogglingBrain(false);
    }
  };

  // Poll state every 3 seconds
  const fetchState = async (sym?: string) => {
    const targetSym = sym || activeSymbol || "XAUUSD";
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/state?symbol=${targetSym}`);
      if (!res.ok) return;
      const data = await res.json();
      setIsLive(data.is_live);
      if (data.active_symbol && !activeSymbol) setActiveSymbol(data.active_symbol);
      if (data.market_regime) setMarketRegime(data.market_regime);
      if (data.online_learning) setOnlineLearning(data.online_learning);
      if (data.next_high_impact_news !== undefined) setNextNews(data.next_high_impact_news);
      if (data.open_positions) setOpenPositions(data.open_positions);
      if (data.portfolio) setPortfolio(data.portfolio);
      if (data.latest_probabilities) setLatestProbs(data.latest_probabilities);

      // Parse brain activation statuses for the target symbol
      if (data.is_normal_active !== undefined) {
        setIsNormalActive(data.is_normal_active);
      } else if (data.models_status?.normal) {
        setIsNormalActive(data.models_status.normal.is_active ?? data.models_status.normal.status?.includes("LIVE"));
      }

      if (data.is_runner_active !== undefined) {
        setIsRunnerActive(data.is_runner_active);
      } else if (data.models_status?.runner) {
        setIsRunnerActive(data.models_status.runner.is_active ?? data.models_status.runner.status?.includes("LIVE"));
      }

      if (data.all_brains_active !== undefined) {
        setAllBrainsActive(data.all_brains_active);
      } else {
        const norm = data.is_normal_active ?? (data.models_status?.normal?.status?.includes("LIVE") || false);
        const run = data.is_runner_active ?? (data.models_status?.runner?.status?.includes("LIVE") || false);
        setAllBrainsActive(norm && run);
      }
    } catch {
      // Backend offline or polling delay
    }
  };

  useEffect(() => {
    fetchState(activeSymbol);
    fetchPairs();
    const interval = setInterval(() => {
      fetchState(activeSymbol);
      fetchPairs();
    }, 3000);
    return () => clearInterval(interval);
  }, [activeSymbol]);

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
            setLogs((prev) => [...prev.slice(-200), msg.message]);
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
        toast.success("AI Autonomous Multi-Pair Trading Engine telah AKTIF.", "Live Execution Active");
      } else {
        toast.info("AI Autonomous Multi-Pair Trading Engine telah DIHENTIKAN.", "Bot Paused");
      }
    } catch {
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

  // Active symbol probabilities resolution
  const currentProbDict = (latestProbs && typeof latestProbs === "object" && activeSymbol in latestProbs)
    ? latestProbs[activeSymbol]
    : latestProbs;

  const normalBuyProb = Math.round((currentProbDict?.normal_buy || 0) * 100);
  const normalSellProb = Math.round((currentProbDict?.normal_sell || 0) * 100);
  const runnerBuyProb = Math.round((currentProbDict?.runner_buy || 0) * 100);
  const runnerSellProb = Math.round((currentProbDict?.runner_sell || 0) * 100);

  const bestBuy = Math.max(normalBuyProb, runnerBuyProb);
  const bestSell = Math.max(normalSellProb, runnerSellProb);
  const dominantDirection = bestBuy > bestSell ? (bestBuy >= 60 ? "BUY" : "NEUTRAL") : (bestSell >= 60 ? "SELL" : "NEUTRAL");

  return (
    <div className="flex flex-col min-h-full lg:h-screen w-full overflow-y-auto lg:overflow-hidden bg-[#070b0a] text-white select-none">
      
      {/* ========================================================================= */}
      {/* 1. TOP QUANT COMMAND RIBBON: Multi-Pair Bar, Portfolio & Bot Master Control */}
      {/* ========================================================================= */}
      <header className="px-3 sm:px-4 py-2 sm:py-2.5 border-b border-white/10 bg-black/60 backdrop-blur-md flex flex-wrap items-center justify-between shrink-0 gap-3 sm:gap-4">
        
        {/* Left: Multi-Pair Badges & Dynamic Switcher */}
        <div className="flex items-center gap-2 overflow-x-auto py-0.5 max-w-full custom-scrollbar">
          <span className="text-[11px] font-bold text-white/40 uppercase tracking-wider flex items-center gap-1.5 shrink-0 mr-1">
            <Sliders size={13} className="text-cyan-400" /> Pairs:
          </span>

          {(pairs.length > 0 ? pairs : [{ symbol: "XAUUSD", is_active: true }]).map((p) => {
            const isSelected = activeSymbol === p.symbol;
            return (
              <div
                key={p.symbol}
                className={`flex items-center rounded-xl border text-xs overflow-hidden transition-all duration-200 shrink-0 ${
                  isSelected 
                    ? "border-cyan-400/80 bg-cyan-950/40 shadow-md shadow-cyan-500/20" 
                    : "border-white/10 bg-white/[0.03] hover:border-white/20"
                }`}
              >
                <button
                  onClick={() => setActiveSymbol(p.symbol)}
                  className={`px-3 py-1.5 font-mono font-bold flex items-center gap-1.5 cursor-pointer ${
                    isSelected ? "text-cyan-300" : "text-white/70 hover:text-white"
                  }`}
                  title={`Tampilkan data telemetri AI untuk ${p.symbol}`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${p.is_active ? "bg-emerald-400 animate-pulse" : "bg-white/30"}`} />
                  <span>{p.symbol}</span>
                </button>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleTogglePair(p.symbol, p.is_active);
                  }}
                  className={`px-2 py-1.5 text-[10px] font-black border-l transition-colors cursor-pointer ${
                    p.is_active
                      ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/30"
                      : "bg-white/5 text-white/40 border-white/10 hover:bg-white/10 hover:text-white/60"
                  }`}
                  title={p.is_active ? `Live trading AKTIF untuk ${p.symbol}. Klik untuk nonaktifkan.` : `Live trading NONAKTIF untuk ${p.symbol}. Klik untuk aktifkan.`}
                >
                  {p.is_active ? "LIVE" : "OFF"}
                </button>

                {p.symbol !== "XAUUSD" && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemovePair(p.symbol);
                    }}
                    className="px-1.5 py-1.5 text-white/30 hover:text-rose-400 hover:bg-rose-500/10 border-l border-white/10 transition-colors"
                    title={`Hapus pair ${p.symbol}`}
                  >
                    <Trash2 size={11} />
                  </button>
                )}
              </div>
            );
          })}

          <button
            onClick={() => setShowAddPairModal(true)}
            className="px-2.5 py-1.5 rounded-xl border border-dashed border-white/20 hover:border-cyan-400/60 bg-white/[0.02] hover:bg-cyan-500/10 text-white/50 hover:text-cyan-300 text-xs font-semibold flex items-center gap-1 transition-all cursor-pointer shrink-0"
            title="Daftarkan pair baru ke sistem"
          >
            <Plus size={13} />
            <span>Tambah Pair</span>
          </button>
        </div>

        {/* Center: Real Financial Telemetry */}
        <div className="flex items-center gap-3 sm:gap-5 text-xs font-mono tabular-nums overflow-x-auto py-0.5 custom-scrollbar shrink-0">
          <div className="flex flex-col">
            <span className="text-[10px] text-white/40 uppercase font-semibold">Balance</span>
            <span className="font-bold text-white text-sm">${balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
          </div>

          <div className="h-6 w-px bg-white/10 hidden sm:block" />

          <div className="flex flex-col">
            <span className="text-[10px] text-white/40 uppercase font-semibold">Equity</span>
            <span className="font-bold text-white text-sm">${equity.toLocaleString("en-US", { minimumFractionDigits: 2 })}</span>
          </div>

          <div className="h-6 w-px bg-white/10 hidden sm:block" />

          <div className="flex flex-col">
            <span className="text-[10px] text-white/40 uppercase font-semibold">Floating PnL</span>
            <span className={`font-bold text-sm ${totalFloatingPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {totalFloatingPnl >= 0 ? "+" : ""}${totalFloatingPnl.toFixed(2)}
            </span>
          </div>

          <div className="h-6 w-px bg-white/10 hidden sm:block" />

          <div className="flex flex-col">
            <span className="text-[10px] text-white/40 uppercase font-semibold">Sekring DD</span>
            <span className={`font-bold text-xs ${currentDrawdown > 15 ? "text-amber-400" : "text-emerald-400"}`}>
              {currentDrawdown.toFixed(1)}% <span className="text-white/40">/ 30%</span>
            </span>
          </div>
        </div>

        {/* Right: Master Bot & Otak Switch */}
        <div className="flex items-center gap-2 sm:gap-2.5 shrink-0 flex-wrap sm:flex-nowrap">
          {/* Quick Master Otak Selector */}
          <select 
            value={
              isNormalActive && isRunnerActive
                ? "all"
                : isNormalActive
                ? "normal"
                : isRunnerActive
                ? "runner"
                : "none"
            } 
            onChange={(e) => {
              const val = e.target.value;
              if (val === "all") handleToggleBrain("all", true);
              else if (val === "none") handleToggleBrain("all", false);
              else if (val === "normal") {
                handleToggleBrain("normal", true);
                handleToggleBrain("runner", false);
              } else if (val === "runner") {
                handleToggleBrain("runner", true);
                handleToggleBrain("normal", false);
              }
            }}
            disabled={isTogglingBrain}
            className="bg-black/60 border border-white/15 text-white/80 text-xs rounded-xl px-2.5 py-1.5 focus:ring-1 focus:ring-emerald-500 outline-none font-medium cursor-pointer"
            title="Pilih mode otak AI aktif"
          >
            <option value="all">🧠 Semua Otak (Scalp + Trend)</option>
            <option value="normal">⚡ Hanya Otak Scalp</option>
            <option value="runner">🚀 Hanya Otak Trend</option>
            <option value="none">🛑 Matikan Semua Otak</option>
          </select>

          <button 
            onClick={toggleLive}
            className={`flex items-center justify-center gap-2 py-2 px-3.5 sm:px-4 rounded-xl transition-all duration-300 font-black text-xs sm:text-sm tracking-wider cursor-pointer shadow-lg ${
              isLive 
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/50 hover:bg-rose-500/30 shadow-rose-500/10' 
                : 'bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold shadow-emerald-500/25'
            }`}
          >
            <Power size={15} className={isLive ? 'animate-pulse' : ''} />
            <span>{isLive ? 'STOP BOT' : 'START BOT'}</span>
          </button>
        </div>
      </header>

      {/* ========================================================================= */}
      {/* 2. MAIN WORKSPACE: Upper Quant Intelligence Grid + Lower Docked Blotter */}
      {/* ========================================================================= */}
      <main className="flex-1 flex flex-col p-3 sm:p-4 gap-4 overflow-y-auto lg:overflow-hidden">
        
        {/* UPPER SECTION: 4 High-Density Quant Intelligence Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4 shrink-0">
          
          {/* Card 1: AI Confidence Radar (Dual-Target LightGBM) with Brain Controls */}
          <div className="rounded-2xl border border-white/10 bg-[#090e0c]/90 backdrop-blur-md p-4 flex flex-col justify-between shadow-xl">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-1.5">
                <Sparkles size={14} className="text-cyan-400" /> AI Confidence &amp; Otak
              </span>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-bold">
                  {activeSymbol}
                </span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold border ${
                  allBrainsActive 
                    ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" 
                    : (isNormalActive || isRunnerActive)
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                    : "bg-rose-500/20 text-rose-400 border-rose-500/30"
                }`}>
                  {allBrainsActive ? "ALL ON" : (isNormalActive || isRunnerActive) ? "PARTIAL" : "ALL OFF"}
                </span>
              </div>
            </div>

            <div className="space-y-2.5 font-mono tabular-nums">
              {/* Scalp Normal Confidence + Otak Toggle */}
              <div className={`p-2.5 rounded-xl border transition-all ${
                isNormalActive ? "bg-black/60 border-emerald-500/30" : "bg-black/40 border-white/5 opacity-70"
              }`}>
                <div className="flex justify-between items-center text-xs mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-sans font-bold text-white/90">Normal Scalp</span>
                    <button
                      type="button"
                      onClick={() => handleToggleBrain("normal", !isNormalActive)}
                      disabled={isTogglingBrain}
                      title={isNormalActive ? "Otak Scalp LIVE. Klik untuk nonaktifkan." : "Otak Scalp OFF. Klik untuk aktifkan."}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider transition-all cursor-pointer flex items-center gap-1 ${
                        isNormalActive
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 shadow-sm shadow-emerald-500/20 hover:bg-emerald-500/30"
                          : "bg-white/10 text-white/40 border border-white/10 hover:text-white hover:bg-white/20"
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${isNormalActive ? "bg-emerald-400 animate-pulse" : "bg-white/30"}`} />
                      <span>{isNormalActive ? "LIVE" : "OFF"}</span>
                    </button>
                  </div>
                  <span className="text-cyan-300 font-bold">{Math.max(normalBuyProb, normalSellProb)}%</span>
                </div>
                <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden flex">
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
                <div className="flex justify-between text-[10px] text-white/40 mt-1">
                  <span className="text-emerald-400/80">BUY: {normalBuyProb}%</span>
                  <span className="text-rose-400/80">SELL: {normalSellProb}%</span>
                </div>
              </div>

              {/* Trend Runner Confidence + Otak Toggle */}
              <div className={`p-2.5 rounded-xl border transition-all ${
                isRunnerActive ? "bg-black/60 border-purple-500/30" : "bg-black/40 border-white/5 opacity-70"
              }`}>
                <div className="flex justify-between items-center text-xs mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-sans font-bold text-white/90">Runner Trend</span>
                    <button
                      type="button"
                      onClick={() => handleToggleBrain("runner", !isRunnerActive)}
                      disabled={isTogglingBrain}
                      title={isRunnerActive ? "Otak Trend LIVE. Klik untuk nonaktifkan." : "Otak Trend OFF. Klik untuk aktifkan."}
                      className={`px-2 py-0.5 rounded text-[10px] font-bold tracking-wider transition-all cursor-pointer flex items-center gap-1 ${
                        isRunnerActive
                          ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-sm shadow-purple-500/20 hover:bg-purple-500/30"
                          : "bg-white/10 text-white/40 border border-white/10 hover:text-white hover:bg-white/20"
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full ${isRunnerActive ? "bg-purple-400 animate-pulse" : "bg-white/30"}`} />
                      <span>{isRunnerActive ? "LIVE" : "OFF"}</span>
                    </button>
                  </div>
                  <span className="text-purple-300 font-bold">{Math.max(runnerBuyProb, runnerSellProb)}%</span>
                </div>
                <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden flex">
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
                <div className="flex justify-between text-[10px] text-white/40 mt-1">
                  <span className="text-emerald-400/80">BUY: {runnerBuyProb}%</span>
                  <span className="text-rose-400/80">SELL: {runnerSellProb}%</span>
                </div>
              </div>
            </div>

            {/* AI Consensus & Master Brain Quick Controls */}
            <div className="mt-2.5 pt-2 border-t border-white/5 flex flex-col gap-2">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-white/40">AI Consensus:</span>
                <span className={`font-bold px-2 py-0.5 rounded text-[10px] tracking-wider ${
                  dominantDirection === "BUY" ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" :
                  dominantDirection === "SELL" ? "bg-rose-500/20 text-rose-400 border border-rose-500/30" :
                  "bg-white/5 text-white/50 border border-white/10"
                }`}>
                  {dominantDirection}
                </span>
              </div>

              {/* Master Brain Toggle Buttons */}
              <div className="flex items-center justify-between pt-1 border-t border-white/5 text-[11px]">
                <span className="text-white/40 text-[10px] uppercase font-bold flex items-center gap-1">
                  <Brain size={12} className="text-brand-green" /> Saklar Otak:
                </span>
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => handleToggleBrain("all", true)}
                    disabled={isTogglingBrain}
                    title="Aktifkan seluruh otak (Scalp 1:2 &amp; Trend 1:5)"
                    className="px-2 py-0.5 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 text-[10px] font-bold transition-all cursor-pointer"
                  >
                    Semua ON
                  </button>
                  <button
                    type="button"
                    onClick={() => handleToggleBrain("all", false)}
                    disabled={isTogglingBrain}
                    title="Nonaktifkan seluruh otak (Quarantine)"
                    className="px-2 py-0.5 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 text-rose-400 border border-rose-500/30 text-[10px] font-bold transition-all cursor-pointer"
                  >
                    Semua OFF
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Card 2: Market Topography & ADX Regime Sensor */}
          <div className="rounded-2xl border border-white/10 bg-[#090e0c]/90 backdrop-blur-md p-4 flex flex-col justify-between shadow-xl">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-1.5">
                <Activity size={14} className="text-indigo-400" /> Market Regime
              </span>
              <span className="text-[10px] font-mono text-white/40">ADX Filter</span>
            </div>

            <div className="space-y-3">
              <div className="bg-black/40 p-3 rounded-xl border border-white/5 flex items-center justify-between">
                <div>
                  <span className="text-[10px] text-white/40 uppercase font-semibold block">Regime Deteksi</span>
                  <span className="text-sm font-bold text-white tracking-wide">{marketRegime.regime}</span>
                </div>
                <div className="text-right font-mono">
                  <span className="text-[10px] text-white/40 uppercase font-semibold block">ADX Value</span>
                  <span className="text-base font-black text-indigo-300">{marketRegime.adx.toFixed(1)}</span>
                </div>
              </div>

              <div className="space-y-1.5 text-xs">
                <div className="flex items-center justify-between text-white/60">
                  <span>Routing Aturan:</span>
                  <span className="font-bold text-white/80">
                    {marketRegime.adx >= 25 ? "Prioritaskan Runner (Trend)" : "Prioritaskan Scalp (Range)"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-white/60">
                  <span>Online Learning:</span>
                  <span className="font-mono text-emerald-400">
                    {onlineLearning.enabled ? "Active (1 Jam)" : "Standby"}
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-2.5 pt-2 border-t border-white/5 flex items-center justify-between">
              <span className="text-[10px] text-white/40 font-mono">
                Last Retrain: {onlineLearning.last_retrain ? onlineLearning.last_retrain.substring(11, 16) : "Ready"}
              </span>
              <button
                onClick={handleTriggerMicroRetrain}
                disabled={isMicroRetraining}
                className="text-[10px] font-bold px-2 py-0.5 rounded bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/40 flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
              >
                <RefreshCw size={10} className={isMicroRetraining ? "animate-spin" : ""} />
                <span>Micro-Retrain</span>
              </button>
            </div>
          </div>

          {/* Card 3: Macro Intelligence & High-Impact News Radar */}
          <div className="rounded-2xl border border-white/10 bg-[#090e0c]/90 backdrop-blur-md p-4 flex flex-col justify-between shadow-xl">
            <NewsCountdown initialEvent={nextNews} />
          </div>

          {/* Card 4: Institutional Risk & Circuit Breaker Health */}
          <div className="rounded-2xl border border-white/10 bg-[#090e0c]/90 backdrop-blur-md p-4 flex flex-col justify-between shadow-xl">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-1.5">
                <ShieldAlert size={14} className="text-emerald-400" /> Risk & Circuit Breaker
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-bold">
                SECURE
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="bg-black/40 p-2.5 rounded-xl border border-white/5 flex justify-between items-center">
                <span className="text-white/60">Risk Lot Mode</span>
                <span className="font-mono font-bold text-white">Fixed 0.01 (Safe)</span>
              </div>
              <div className="bg-black/40 p-2.5 rounded-xl border border-white/5 flex justify-between items-center">
                <span className="text-white/60">Anti-Hedging Rule</span>
                <span className="font-bold text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 size={12} /> Active
                </span>
              </div>
              <div className="bg-black/40 p-2.5 rounded-xl border border-white/5 flex justify-between items-center">
                <span className="text-white/60">Friday Liquidator</span>
                <span className="font-mono font-semibold text-white/80">Sabtu 00:00 WIB (1x)</span>
              </div>
            </div>

            <div className="mt-2.5 pt-2 border-t border-white/5 flex items-center justify-between text-[10px] text-white/40">
              <span>Fat-Finger Cap: Max 0.10 Lot</span>
              <span>Spread Limit: Dynamic</span>
            </div>
          </div>

        </div>

        {/* LOWER SECTION: Expanded Full-Width Institutional Docked Blotter */}
        <div className="flex-1 min-h-[420px] lg:min-h-0 flex flex-col rounded-2xl border border-white/10 bg-[#090e0c]/95 overflow-hidden shadow-2xl">
          
          {/* Blotter Navigation Header */}
          <div className="px-3 sm:px-4 py-2 border-b border-white/10 bg-black/50 flex items-center justify-between text-xs shrink-0 overflow-x-auto scrollbar-none gap-2">
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => setBlotterTab("positions")}
                className={`px-3 py-1.5 rounded-xl font-bold text-xs flex items-center gap-2 transition-all cursor-pointer ${
                  blotterTab === "positions"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm shadow-emerald-500/20"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <Layers size={14} />
                <span>Open Positions</span>
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-white/10 text-white font-mono tabular-nums">
                  {openPositions.length}
                </span>
              </button>

              <button
                onClick={() => setBlotterTab("telemetry")}
                className={`px-3 py-1.5 rounded-xl font-bold text-xs flex items-center gap-2 transition-all cursor-pointer ${
                  blotterTab === "telemetry"
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/20"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <Activity size={14} />
                <span>Account Telemetry</span>
              </button>

              <button
                onClick={() => setBlotterTab("logs")}
                className={`px-3 py-1.5 rounded-xl font-bold text-xs flex items-center gap-2 transition-all cursor-pointer ${
                  blotterTab === "logs"
                    ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-sm shadow-purple-500/20"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <Terminal size={14} />
                <span>Live Event Feed</span>
              </button>

              <button
                onClick={() => setBlotterTab("pairs")}
                className={`px-3 py-1.5 rounded-xl font-bold text-xs flex items-center gap-2 transition-all cursor-pointer ${
                  blotterTab === "pairs"
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm shadow-amber-500/20"
                    : "text-white/50 hover:text-white"
                }`}
              >
                <Database size={14} />
                <span>Multi-Pair Health</span>
              </button>
            </div>

            <div className="flex items-center gap-3 text-white/40 text-[11px] font-mono shrink-0">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400" /> MT5 Live Bridge
              </span>
            </div>
          </div>

          {/* Blotter Content Viewport */}
          <div className="flex-1 overflow-hidden relative">
            
            {/* TAB 1: Live Open Positions Table & Mobile Cards */}
            {blotterTab === "positions" && (
              <div className="w-full h-full overflow-y-auto custom-scrollbar">
                {openPositions.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center p-6 text-center">
                    <div className="w-12 h-12 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center text-white/30 mb-3">
                      <ShieldCheck size={24} className="text-emerald-400/60" />
                    </div>
                    <span className="text-sm font-semibold text-white/60">Tidak ada posisi terbuka di broker MT5</span>
                    <span className="text-xs text-white/30 font-mono mt-1 max-w-md">
                      Semua parameter risiko aman. Mesin otonom memantau setup BBMA Re-entry dan probabilitas AI untuk seluruh pair aktif.
                    </span>
                  </div>
                ) : (
                  <>
                    {/* Mobile Card Layout for Open Positions */}
                    <div className="block md:hidden p-3 space-y-3">
                      {openPositions.map((pos) => {
                        const isBuy = pos.type === "BUY";
                        const isProfit = pos.profit >= 0;
                        const isLoading = !!actionLoadingTicket[pos.ticket];

                        return (
                          <div key={pos.ticket} className="bg-black/50 border border-white/10 rounded-xl p-3 flex flex-col gap-2">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs text-white/40 font-mono">#{pos.ticket}</span>
                                <span className="font-bold text-xs text-white font-mono">{pos.symbol || activeSymbol}</span>
                                <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                                  isBuy ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                                }`}>
                                  {pos.type}
                                </span>
                              </div>
                              <span className={`text-xs font-bold font-mono ${isProfit ? "text-emerald-400" : "text-rose-400"}`}>
                                {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
                              </span>
                            </div>

                            <div className="grid grid-cols-4 gap-1.5 text-[10px] pt-1.5 border-t border-white/5 font-mono text-white/60">
                              <div>
                                <span className="text-white/30 block">Vol</span>
                                <span className="text-white/80 font-bold">{(pos.volume || 0).toFixed(2)}</span>
                              </div>
                              <div>
                                <span className="text-white/30 block">Entry</span>
                                <span className="text-white/80">{(pos.open_price || 0).toFixed((pos.open_price || 0) > 100 ? 2 : 5)}</span>
                              </div>
                              <div>
                                <span className="text-white/30 block">Current</span>
                                <span className="text-white/90 font-bold">{(pos.current_price || 0).toFixed((pos.current_price || 0) > 100 ? 2 : 5)}</span>
                              </div>
                              <div>
                                <span className="text-white/30 block">SL/TP</span>
                                <span className="text-white/60">{pos.sl ? Number(pos.sl).toFixed(1) : "-"}</span>
                              </div>
                            </div>

                            <div className="flex items-center gap-1.5 pt-1.5 border-t border-white/5">
                              <button
                                onClick={() => handlePositionAction(pos.ticket, "break-even", pos.symbol)}
                                disabled={isLoading}
                                className="flex-1 py-1 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold flex items-center justify-center gap-1 disabled:opacity-40 cursor-pointer"
                              >
                                <ShieldCheck size={11} /> BE
                              </button>
                              <button
                                onClick={() => handlePositionAction(pos.ticket, "partial-close", pos.symbol)}
                                disabled={isLoading}
                                className="flex-1 py-1 rounded bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-bold flex items-center justify-center gap-1 disabled:opacity-40 cursor-pointer"
                              >
                                <Scissors size={11} /> 50%
                              </button>
                              <button
                                onClick={() => handlePositionAction(pos.ticket, "close", pos.symbol)}
                                disabled={isLoading}
                                className="flex-1 py-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-[10px] font-bold flex items-center justify-center gap-1 disabled:opacity-40 cursor-pointer"
                              >
                                <XCircle size={11} /> Close
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    {/* Desktop Table View */}
                    <div className="hidden md:block">
                      <table className="w-full text-left text-xs font-mono tabular-nums">
                        <thead className="sticky top-0 bg-[#070b0a] border-b border-white/10 text-white/40 uppercase text-[10px] tracking-wider z-10">
                          <tr>
                            <th className="py-3 px-4">Ticket</th>
                            <th className="py-3 px-4">Symbol</th>
                            <th className="py-3 px-4">Type</th>
                            <th className="py-3 px-4">Volume</th>
                            <th className="py-3 px-4">Open Price</th>
                            <th className="py-3 px-4">Current Price</th>
                            <th className="py-3 px-4">SL / TP</th>
                            <th className="py-3 px-4 text-right">Profit / Loss</th>
                            <th className="py-3 px-4 text-center">Fast Action Guard</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-white/5">
                          {openPositions.map((pos) => {
                            const isBuy = pos.type === "BUY";
                            const isProfit = pos.profit >= 0;
                            const isLoading = !!actionLoadingTicket[pos.ticket];

                            return (
                              <tr key={pos.ticket} className="hover:bg-white/[0.03] transition-colors">
                                <td className="py-3 px-4 text-white/40">#{pos.ticket}</td>
                                <td className="py-3 px-4 font-mono font-bold text-white/90">
                                  <span className="px-2 py-0.5 rounded-lg bg-white/5 border border-white/10 text-xs">
                                    {pos.symbol || activeSymbol}
                                  </span>
                                </td>
                                <td className="py-3 px-4">
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                    isBuy ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                                  }`}>
                                    {pos.type}
                                  </span>
                                </td>

                                <td className="py-3 px-4 text-white/80 font-bold">{(pos.volume || 0).toFixed(2)}</td>
                                <td className="py-3 px-4 text-white/80">{(pos.open_price || 0).toFixed((pos.open_price || 0) > 100 ? 2 : 5)}</td>
                                <td className="py-3 px-4 font-bold text-white">{(pos.current_price || 0).toFixed((pos.current_price || 0) > 100 ? 2 : 5)}</td>
                                <td className="py-3 px-4 text-white/60">
                                  {pos.sl ? Number(pos.sl).toFixed((pos.sl || 0) > 100 ? 2 : 5) : "-"} / {pos.tp ? Number(pos.tp).toFixed((pos.tp || 0) > 100 ? 2 : 5) : "-"}
                                </td>
                                <td className={`py-3 px-4 text-right font-black text-sm ${
                                  isProfit ? "text-emerald-400" : "text-rose-400"
                                }`}>
                                  {isProfit ? "+" : ""}${pos.profit.toFixed(2)}
                                </td>
                                <td className="py-3 px-4">
                                  <div className="flex items-center justify-center gap-1.5">
                                    <button
                                      onClick={() => handlePositionAction(pos.ticket, "break-even", pos.symbol)}
                                      disabled={isLoading}
                                      title="Geser SL ke Break-Even (BE)"
                                      className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                                    >
                                      <ShieldCheck size={12} /> BE
                                    </button>
                                    <button
                                      onClick={() => handlePositionAction(pos.ticket, "partial-close", pos.symbol)}
                                      disabled={isLoading}
                                      title="Tutup 50% Volume"
                                      className="px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                                    >
                                      <Scissors size={12} /> 50%
                                    </button>
                                    <button
                                      onClick={() => handlePositionAction(pos.ticket, "close", pos.symbol)}
                                      disabled={isLoading}
                                      title="Tutup Posisi Penuh"
                                      className="px-2.5 py-1 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-[10px] font-bold flex items-center gap-1 transition-all disabled:opacity-40 cursor-pointer"
                                    >
                                      <XCircle size={12} /> Close
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* TAB 2: Account Telemetry */}
            {blotterTab === "telemetry" && (
              <div className="p-4 sm:p-6 grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 h-full overflow-y-auto custom-scrollbar font-mono tabular-nums">
                <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-[10px] uppercase font-bold text-white/40">Balance Modal</span>
                  <span className="text-xl font-black text-white">${balance.toFixed(2)}</span>
                  <span className="text-[10px] text-white/40">Modal riil di server broker</span>
                </div>

                <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-[10px] uppercase font-bold text-white/40">Equity Berjalan</span>
                  <span className="text-xl font-black text-white">${equity.toFixed(2)}</span>
                  <span className="text-[10px] text-white/40">Nilai ekuitas real-time MT5</span>
                </div>

                <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-[10px] uppercase font-bold text-white/40">Floating PnL</span>
                  <span className={`text-xl font-black ${totalFloatingPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {totalFloatingPnl >= 0 ? "+" : ""}${totalFloatingPnl.toFixed(2)}
                  </span>
                  <span className="text-[10px] text-white/40">{openPositions.length} posisi terbuka</span>
                </div>

                <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-[10px] uppercase font-bold text-white/40">Circuit Breaker Drawdown</span>
                  <span className="text-xl font-black text-emerald-400">
                    {currentDrawdown.toFixed(1)}% <span className="text-xs text-white/40">/ 30.0%</span>
                  </span>
                  <span className="text-[10px] text-white/40">Batas rugi maksimal darurat</span>
                </div>
              </div>
            )}


            {/* TAB 3: Live Event Terminal Log Feed */}
            {blotterTab === "logs" && (
              <div 
                ref={logsScrollRef}
                className="w-full h-full p-4 font-mono text-xs overflow-y-auto custom-scrollbar bg-black/80 flex flex-col gap-1.5"
              >
                {logs.length === 0 ? (
                  <span className="text-white/30 italic">Menghubungkan ke streaming log AI Autonomous Engine...</span>
                ) : (
                  logs.map((log, i) => {
                    const isWarning = log.includes("WARNING");
                    const isError = log.includes("ERROR");
                    const isSignal = log.includes("[SIGNAL]");
                    const isSekring = log.includes("[SEKRING]");
                    let colorClass = "text-white/70";
                    if (isSignal) colorClass = "text-emerald-300 font-bold bg-emerald-950/20";
                    else if (isSekring) colorClass = "text-amber-300 font-bold bg-amber-950/20";
                    else if (isWarning) colorClass = "text-yellow-400 font-bold";
                    else if (isError) colorClass = "text-rose-400 font-bold";
                    return (
                      <div key={i} className={`${colorClass} hover:bg-white/5 px-2 py-0.5 rounded break-all`}>
                        {log}
                      </div>
                    );
                  })
                )}
              </div>
            )}

            {/* TAB 4: Multi-Pair Health & Datasets */}
            {blotterTab === "pairs" && (
              <div className="w-full h-full overflow-y-auto custom-scrollbar p-6">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {pairs.map((p) => (
                    <div key={p.symbol} className="bg-black/40 border border-white/10 rounded-2xl p-4 flex flex-col justify-between gap-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-base font-bold font-mono text-white">{p.symbol}</span>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-white/50 font-mono">
                            Broker: {p.broker_symbol}
                          </span>
                        </div>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          p.is_active ? "bg-emerald-500/20 text-emerald-400" : "bg-white/10 text-white/40"
                        }`}>
                          {p.is_active ? "LIVE ACTIVE" : "OFF"}
                        </span>
                      </div>

                      <div className="space-y-1.5 text-xs font-mono">
                        <div className="flex justify-between text-white/60">
                          <span>Database Table:</span>
                          <span className="text-white/80">{p.table_name}</span>
                        </div>
                        <div className="flex justify-between text-white/60">
                          <span>Candles Tersimpan:</span>
                          <span className="text-cyan-300 font-bold">{p.row_count?.toLocaleString() || 0}</span>
                        </div>
                        <div className="flex justify-between text-white/60">
                          <span>Normal Model:</span>
                          <span className={p.has_normal_model ? "text-emerald-400" : "text-white/30"}>
                            {p.has_normal_model ? `Trained (${(p.last_accuracy_normal * 100).toFixed(0)}%)` : "Not Trained"}
                          </span>
                        </div>
                        <div className="flex justify-between text-white/60">
                          <span>Runner Model:</span>
                          <span className={p.has_runner_model ? "text-purple-400" : "text-white/30"}>
                            {p.has_runner_model ? `Trained (${(p.last_accuracy_runner * 100).toFixed(0)}%)` : "Not Trained"}
                          </span>
                        </div>
                      </div>

                      <div className="pt-2 border-t border-white/5 flex items-center justify-between">
                        <button
                          onClick={() => handleTogglePair(p.symbol, p.is_active)}
                          className={`text-xs font-bold px-3 py-1 rounded-xl transition-all cursor-pointer ${
                            p.is_active
                              ? "bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30"
                              : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          }`}
                        >
                          {p.is_active ? "Nonaktifkan" : "Aktifkan Trading"}
                        </button>
                        {p.symbol !== "XAUUSD" && (
                          <button
                            onClick={() => handleRemovePair(p.symbol)}
                            className="text-xs text-white/30 hover:text-rose-400 transition-colors cursor-pointer"
                          >
                            Hapus Pair
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        </div>

      </main>

      {/* ========================================================================= */}
      {/* 3. MODAL: Tambah Pair Baru */}
      {/* ========================================================================= */}
      {showAddPairModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#0b100e] border border-white/15 rounded-3xl p-6 w-full max-w-md shadow-2xl relative">
            <div className="flex items-center justify-between mb-4">
              <span className="text-base font-bold text-white flex items-center gap-2">
                <Plus size={18} className="text-cyan-400" /> Daftarkan Pair Baru
              </span>
              <button 
                onClick={() => setShowAddPairModal(false)}
                className="text-white/40 hover:text-white transition-colors"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleAddPair} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-white/60 mb-1.5">
                  Symbol Pair (contoh: EURUSD, GBPUSD, USDJPY, BTCUSD)
                </label>
                <input
                  type="text"
                  value={newPairInput}
                  onChange={(e) => setNewPairInput(e.target.value.toUpperCase())}
                  placeholder="EURUSD"
                  className="w-full bg-black/60 border border-white/15 rounded-xl px-3.5 py-2.5 text-white font-mono text-sm focus:border-cyan-400 outline-none uppercase"
                  autoFocus
                />
                <p className="text-[11px] text-white/40 mt-1.5">
                  Sistem otomatis mendeteksi suffix broker Anda (contoh: EURUSDm, EURUSDc) dan membuatkan subfolder otak terisolasi <code className="text-cyan-300">models/{newPairInput || "PAIR"}/</code>.
                </p>
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddPairModal(false)}
                  className="px-4 py-2 rounded-xl text-xs font-semibold text-white/60 hover:text-white bg-white/5 hover:bg-white/10 transition-all cursor-pointer"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={isAddingPair || !newPairInput.trim()}
                  className="px-5 py-2 rounded-xl text-xs font-bold text-black bg-cyan-400 hover:bg-cyan-300 transition-all disabled:opacity-40 cursor-pointer shadow-lg shadow-cyan-500/20"
                >
                  {isAddingPair ? "Mendaftarkan..." : "Daftarkan Pair"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
