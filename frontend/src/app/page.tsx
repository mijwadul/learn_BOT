"use client";

import { useState, useEffect, useRef } from "react";
import { Layers, Activity, Terminal, Database } from "lucide-react";
import { getApiBaseUrl, getWsBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import { ConfirmModal } from "@/components/ui/ConfirmModal";
import { MacroEvent } from "@/components/NewsCountdown";
import {
  DashboardHeader,
  BrainTelemetryGrid,
  OpenPositionsTable,
  LiveTerminalLogs,
  MultiPairHealthGrid,
  AddPairModal,
} from "@/components/dashboard";

export default function Home() {
  const toast = useToast();
  const [isLive, setIsLive] = useState(false);
  const [selectedMode] = useState("auto");
  const [activeSymbol, setActiveSymbol] = useState<string>("BTCUSD");
  const [pairs, setPairs] = useState<any[]>([
    { symbol: "BTCUSD", is_active: true },
    { symbol: "XAUUSD", is_active: false },
  ]);
  const [showAddPairModal, setShowAddPairModal] = useState(false);
  const [newPairInput, setNewPairInput] = useState("");
  const [isAddingPair, setIsAddingPair] = useState(false);
  const [pairToDelete, setPairToDelete] = useState<string | null>(null);
  const [isDeletingPair, setIsDeletingPair] = useState(false);

  // Strategy Brain (Otak) states
  const [isNormalActive, setIsNormalActive] = useState(false);
  const [isRunnerActive, setIsRunnerActive] = useState(false);
  const [allBrainsActive, setAllBrainsActive] = useState(false);
  const [isTogglingBrain, setIsTogglingBrain] = useState(false);

  const [marketRegime, setMarketRegime] = useState<{ adx: number; regime: string }>({
    adx: 0,
    regime: "DETECTING...",
  });
  const [onlineLearning, setOnlineLearning] = useState<{
    enabled: boolean;
    last_retrain: string | null;
  }>({ enabled: true, last_retrain: null });
  const [isMicroRetraining, setIsMicroRetraining] = useState(false);
  const [nextNews, setNextNews] = useState<MacroEvent | null>(null);
  const [openPositions, setOpenPositions] = useState<any[]>([]);
  const [portfolio, setPortfolio] = useState<{ value: number; equity: number }>({
    value: 10000,
    equity: 10000,
  });
  const [latestProbs, setLatestProbs] = useState<any>({
    normal_buy: 0.0,
    normal_sell: 0.0,
    runner_buy: 0.0,
    runner_sell: 0.0,
    normal: 0.5,
    runner: 0.5,
  });

  // Docked Blotter Navigation & Logs State
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
        const currentActive = data.pairs.find((p: any) => p.symbol === activeSymbol);
        if (!currentActive || !currentActive.is_active) {
          const firstLive = data.pairs.find((p: any) => p.is_active);
          if (firstLive) {
            setActiveSymbol(firstLive.symbol);
            fetchState(firstLive.symbol);
          }
        }
      }
    } catch {
      // Backend offline or polling delay
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

  const handleRemovePair = (symbol: string) => {
    if (symbol === "XAUUSD") return;
    setPairToDelete(symbol);
  };

  const confirmDeletePair = async () => {
    if (!pairToDelete || pairToDelete === "XAUUSD") return;
    setIsDeletingPair(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/pairs/remove`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: pairToDelete }),
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.info(data.message, "Pair Dihapus");
        if (activeSymbol === pairToDelete) setActiveSymbol("XAUUSD");
        fetchPairs();
      } else {
        toast.error(data.message, "Gagal Hapus");
      }
    } catch {
      toast.error("Gagal menghapus pair.", "Error");
    } finally {
      setIsDeletingPair(false);
      setPairToDelete(null);
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

  const handlePositionAction = async (
    ticket: number,
    actionType: "break-even" | "partial-close" | "close",
    symbol?: string
  ) => {
    setActionLoadingTicket((prev) => ({ ...prev, [ticket]: actionType }));
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/positions/${actionType}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticket, symbol: symbol || activeSymbol }),
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
  const currentProbDict =
    latestProbs && typeof latestProbs === "object" && activeSymbol in latestProbs
      ? latestProbs[activeSymbol]
      : latestProbs;

  const normalBuyProb = Math.round((currentProbDict?.normal_buy || 0) * 100);
  const normalSellProb = Math.round((currentProbDict?.normal_sell || 0) * 100);
  const runnerBuyProb = Math.round((currentProbDict?.runner_buy || 0) * 100);
  const runnerSellProb = Math.round((currentProbDict?.runner_sell || 0) * 100);

  const bestBuy = Math.max(normalBuyProb, runnerBuyProb);
  const bestSell = Math.max(normalSellProb, runnerSellProb);
  const dominantDirection =
    bestBuy > bestSell ? (bestBuy >= 60 ? "BUY" : "NEUTRAL") : bestSell >= 60 ? "SELL" : "NEUTRAL";

  return (
    <div className="flex flex-col min-h-full lg:h-screen w-full overflow-y-auto lg:overflow-hidden bg-[#070b0a] text-white select-none">
      {/* 1. TOP QUANT COMMAND RIBBON */}
      <DashboardHeader
        pairs={pairs}
        activeSymbol={activeSymbol}
        setActiveSymbol={setActiveSymbol}
        handleTogglePair={handleTogglePair}
        handleRemovePair={handleRemovePair}
        setShowAddPairModal={setShowAddPairModal}
        balance={balance}
        equity={equity}
        totalFloatingPnl={totalFloatingPnl}
        currentDrawdown={currentDrawdown}
        isNormalActive={isNormalActive}
        isRunnerActive={isRunnerActive}
        isTogglingBrain={isTogglingBrain}
        handleToggleBrain={handleToggleBrain}
        isLive={isLive}
        toggleLive={toggleLive}
      />

      {/* 2. MAIN WORKSPACE */}
      <main className="flex-1 flex flex-col p-3 sm:p-4 gap-4 overflow-y-auto lg:overflow-hidden">
        {/* Upper: 4 Quant Intelligence & Brain Cards */}
        <BrainTelemetryGrid
          activeSymbol={activeSymbol}
          allBrainsActive={allBrainsActive}
          isNormalActive={isNormalActive}
          isRunnerActive={isRunnerActive}
          isTogglingBrain={isTogglingBrain}
          handleToggleBrain={handleToggleBrain}
          normalBuyProb={normalBuyProb}
          normalSellProb={normalSellProb}
          runnerBuyProb={runnerBuyProb}
          runnerSellProb={runnerSellProb}
          dominantDirection={dominantDirection}
          marketRegime={marketRegime}
          onlineLearning={onlineLearning}
          handleTriggerMicroRetrain={handleTriggerMicroRetrain}
          isMicroRetraining={isMicroRetraining}
          nextNews={nextNews}
        />

        {/* Lower: Institutional Docked Blotter */}
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
            {blotterTab === "positions" && (
              <OpenPositionsTable
                openPositions={openPositions}
                activeSymbol={activeSymbol}
                actionLoadingTicket={actionLoadingTicket}
                handlePositionAction={handlePositionAction}
              />
            )}

            {blotterTab === "telemetry" && (
              <div className="p-4 sm:p-6 grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 h-full overflow-y-auto custom-scrollbar font-mono tabular-nums">
                <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-[10px] uppercase font-bold text-white/40">Balance Modal</span>
                  <span className="text-xl font-black text-white">${balance.toFixed(2)}</span>
                </div>
                <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-[10px] uppercase font-bold text-white/40">Equity Berjalan</span>
                  <span className="text-xl font-black text-white">${equity.toFixed(2)}</span>
                </div>
                <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-[10px] uppercase font-bold text-white/40">Floating PnL</span>
                  <span className={`text-xl font-black ${totalFloatingPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {totalFloatingPnl >= 0 ? "+" : ""}${totalFloatingPnl.toFixed(2)}
                  </span>
                </div>
                <div className="bg-black/40 border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
                  <span className="text-[10px] uppercase font-bold text-white/40">Circuit Breaker Drawdown</span>
                  <span className="text-xl font-black text-emerald-400">
                    {currentDrawdown.toFixed(1)}% <span className="text-xs text-white/40">/ 30.0%</span>
                  </span>
                </div>
              </div>
            )}

            {blotterTab === "logs" && (
              <LiveTerminalLogs logs={logs} logsScrollRef={logsScrollRef} />
            )}

            {blotterTab === "pairs" && (
              <MultiPairHealthGrid
                pairs={pairs}
                handleTogglePair={handleTogglePair}
                handleRemovePair={handleRemovePair}
              />
            )}
          </div>
        </div>
      </main>

      {/* 3. MODALS */}
      <AddPairModal
        isOpen={showAddPairModal}
        onClose={() => setShowAddPairModal(false)}
        onAddPair={handleAddPair}
        newPairInput={newPairInput}
        setNewPairInput={setNewPairInput}
        isAddingPair={isAddingPair}
      />

      <ConfirmModal
        isOpen={!!pairToDelete}
        onClose={() => setPairToDelete(null)}
        onConfirm={confirmDeletePair}
        title={`Hapus Pair ${pairToDelete}`}
        description={`Apakah Anda yakin ingin menghapus ${pairToDelete} dari pemantauan bot? Bot tidak akan lagi memonitor atau mengeksekusi order untuk pair ini.`}
        confirmText="Hapus Pair"
        cancelText="Batal"
        variant="danger"
        isLoading={isDeletingPair}
      />
    </div>
  );
}
