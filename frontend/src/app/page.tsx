"use client";

import { useState, useEffect } from "react";
import { Power, Sliders, DollarSign, Percent, Check } from "lucide-react";
import dynamic from "next/dynamic";

// Dynamically import TradingChart to avoid SSR issues with canvas
const TradingChart = dynamic(() => import("@/components/TradingChart"), { ssr: false });

export default function Home() {
  const [isLive, setIsLive] = useState(false);
  const [selectedMode, setSelectedMode] = useState("auto");
  const [logs, setLogs] = useState<string[]>([]);
  const [portfolio, setPortfolio] = useState({ value: 0, equity: 0 });
  const [metrics, setMetrics] = useState({
    win_rate: 0,
    total_trades: 0,
    avg_profit: 0,
    max_drawdown: 0
  });
  const [marketRegime, setMarketRegime] = useState<{ adx: number; regime: string }>({ adx: 0, regime: "DETECTING..." });
  const [onlineLearning, setOnlineLearning] = useState<{ enabled: boolean; last_retrain: string | null }>({ enabled: true, last_retrain: null });

  // Risk Management State
  const [riskMode, setRiskMode] = useState<"dollars" | "percent">("dollars");
  const [riskDollars, setRiskDollars] = useState(10.0);
  const [riskPercent, setRiskPercent] = useState(1.0);
  const [isSavingRisk, setIsSavingRisk] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [hasLoadedRiskOnce, setHasLoadedRiskOnce] = useState(false);

  useEffect(() => {
    const fetchState = () => {
      fetch("http://localhost:8000/api/state")
        .then(res => res.json())
        .then(data => {
          setIsLive(data.is_live);
          setMetrics(data.performance);
          setPortfolio(data.portfolio);
          if (data.market_regime) setMarketRegime(data.market_regime);
          if (data.online_learning) setOnlineLearning(data.online_learning);
          if (data.risk_settings && !hasLoadedRiskOnce) {
            setRiskMode(data.risk_settings.mode || "dollars");
            setRiskDollars(data.risk_settings.dollars || 10.0);
            setRiskPercent(data.risk_settings.percent || 1.0);
            setHasLoadedRiskOnce(true);
          }
        })
        .catch(err => console.error("Backend offline", err));
    };
    fetchState();
    const interval = setInterval(fetchState, 3000);
    return () => clearInterval(interval);
  }, [hasLoadedRiskOnce]);

  const effectiveRiskDollars = riskMode === "dollars"
    ? riskDollars
    : ((portfolio.equity > 0 ? portfolio.equity : 1000) * riskPercent) / 100;

  const handleSaveRisk = async () => {
    setIsSavingRisk(true);
    try {
      const res = await fetch("http://localhost:8000/api/settings/risk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          risk_mode: riskMode,
          risk_dollars: riskDollars,
          risk_percent: riskPercent
        })
      });
      if (res.ok) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 2500);
      }
    } catch (err) {
      console.error("Failed to update risk settings", err);
    } finally {
      setIsSavingRisk(false);
    }
  };

  const toggleLive = async () => {
    try {
      if (!isLive && selectedMode !== "auto") {
         await fetch("http://localhost:8000/api/strategies/force_live", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: selectedMode.replace("force_", "") })
         });
      }
      const res = await fetch("http://localhost:8000/api/state/toggle", { method: "POST" });
      const data = await res.json();
      setIsLive(data.is_live);
    } catch (err) {
      console.error("Failed to toggle state", err);
    }
  };

  return (
    <div className="p-6 flex flex-col gap-6 h-screen">
      
      {/* Top Row: Left Column (Stats) & Right Column (Chart) */}
      <div className="flex flex-col lg:flex-row gap-6 flex-1 min-h-0">
        
        {/* Left Column: Stats & Controls */}
        <div className="w-full lg:w-80 flex flex-col gap-6 overflow-y-auto shrink-0">
          
          {/* AI Bot State */}
          <div className="glass-panel p-6 flex flex-col items-center justify-center relative overflow-hidden shrink-0">
            <h2 className="text-xs font-semibold uppercase text-white/50 mb-6 tracking-wider w-full text-left">AI Bot State</h2>
            
            {!isLive && (
              <select 
                value={selectedMode} 
                onChange={(e) => setSelectedMode(e.target.value)}
                className="mb-4 w-full bg-black/40 border border-white/10 text-white text-sm rounded-lg p-2 focus:ring-brand-green focus:border-brand-green outline-none"
              >
                <option value="auto">Auto (Strict OOS)</option>
                <option value="force_normal">Forced Live: Normal Mode</option>
                <option value="force_runner">Forced Live: Runner Mode</option>
              </select>
            )}

            <button 
              onClick={toggleLive}
              className={`relative flex items-center justify-center gap-3 px-8 py-4 rounded-2xl transition-all duration-300 w-full ${isLive ? 'bg-brand-green/20 text-brand-green glow-green' : 'bg-white/5 text-white/40 hover:bg-white/10'}`}
            >
              <Power size={24} className={isLive ? 'animate-pulse' : ''} />
              <span className="font-black text-2xl tracking-widest">{isLive ? 'LIVE' : 'START'}</span>
            </button>
            <p className="text-xs text-white/40 mt-6 font-medium">
              {isLive ? 'Active Since: Just now' : 'System is currently paused'}
            </p>
          </div>

          {/* Risk Management Setting ($ / %) */}
          <div className="glass-panel p-5 shrink-0">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold uppercase text-white/50 tracking-wider flex items-center gap-1.5">
                <Sliders size={14} className="text-brand-green" />
                <span>Risk Per Trade</span>
              </h2>
              {saveSuccess && (
                <span className="text-[10px] text-brand-green flex items-center gap-1 bg-brand-green/20 px-2 py-0.5 rounded font-bold">
                  <Check size={12} /> Saved
                </span>
              )}
            </div>

            {/* Toggle Mode: Dollars vs Percent */}
            <div className="grid grid-cols-2 gap-2 mb-3 bg-black/40 p-1 rounded-xl border border-white/5">
              <button
                type="button"
                onClick={() => setRiskMode("dollars")}
                className={`flex items-center justify-center gap-1 py-1.5 text-xs font-bold rounded-lg transition-all ${
                  riskMode === "dollars"
                    ? "bg-brand-green/20 text-brand-green border border-brand-green/30"
                    : "text-white/40 hover:text-white/70"
                }`}
              >
                <DollarSign size={13} />
                <span>Fixed ($)</span>
              </button>
              <button
                type="button"
                onClick={() => setRiskMode("percent")}
                className={`flex items-center justify-center gap-1 py-1.5 text-xs font-bold rounded-lg transition-all ${
                  riskMode === "percent"
                    ? "bg-brand-green/20 text-brand-green border border-brand-green/30"
                    : "text-white/40 hover:text-white/70"
                }`}
              >
                <Percent size={13} />
                <span>Percent (%)</span>
              </button>
            </div>

            {/* Value Input */}
            <div className="flex items-center gap-2 mb-2">
              <div className="relative flex-1">
                <input
                  type="number"
                  step={riskMode === "dollars" ? "1" : "0.1"}
                  min="0.1"
                  max={riskMode === "dollars" ? "5000" : "15"}
                  value={riskMode === "dollars" ? riskDollars : riskPercent}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value) || 0;
                    if (riskMode === "dollars") setRiskDollars(val);
                    else setRiskPercent(val);
                  }}
                  className="w-full bg-black/40 border border-white/10 text-white font-mono font-bold text-sm rounded-lg px-3 py-2 focus:ring-1 focus:ring-brand-green focus:border-brand-green outline-none"
                />
                <span className="absolute right-3 top-2 text-xs font-bold text-white/40">
                  {riskMode === "dollars" ? "USD" : "%"}
                </span>
              </div>
              <button
                type="button"
                onClick={handleSaveRisk}
                disabled={isSavingRisk}
                className="bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/30 font-bold text-xs px-4 py-2 rounded-lg transition-all shrink-0 disabled:opacity-50"
              >
                {isSavingRisk ? "..." : "Save"}
              </button>
            </div>

            {/* Quick Presets */}
            <div className="flex gap-1.5 mb-3">
              {(riskMode === "dollars" ? [5, 10, 20, 50] : [0.5, 1.0, 2.0, 3.0]).map((preset) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => {
                    if (riskMode === "dollars") setRiskDollars(preset);
                    else setRiskPercent(preset);
                  }}
                  className="flex-1 py-1 text-[11px] font-mono bg-white/5 hover:bg-white/10 text-white/60 hover:text-white rounded border border-white/5 transition-all text-center"
                >
                  {riskMode === "dollars" ? `$${preset}` : `${preset}%`}
                </button>
              ))}
            </div>

            {/* Effective Risk Realtime Preview */}
            <div className="bg-white/5 rounded-lg p-2.5 flex justify-between items-center text-xs">
              <span className="text-white/50">Risk Efektif:</span>
              <span className="font-mono font-bold text-brand-green">
                ${effectiveRiskDollars.toFixed(2)}
              </span>
            </div>
          </div>

          {/* Performance Metrics */}
          <div className="glass-panel p-6 shrink-0 mb-4">
            <h2 className="text-xs font-semibold uppercase text-white/50 mb-6 tracking-wider">Performance Metrics</h2>
            <div className="flex justify-center mb-8">
              <div className="w-32 h-32 rounded-full border-4 border-brand-green flex flex-col items-center justify-center relative glow-green">
                <span className="text-[10px] text-white/50 font-bold uppercase mb-1">Win Rate</span>
                <span className="text-3xl font-black text-white">{metrics.win_rate}%</span>
              </div>
            </div>
            <div className="space-y-4">
              <MetricRow label="Total Trades" value={metrics.total_trades} />
              <MetricRow label="Avg Profit" value={`$${metrics.avg_profit}`} color="text-brand-green" />
              <MetricRow label="Max Drawdown" value={`${metrics.max_drawdown}%`} color="text-brand-red" />
            </div>
          </div>

          {/* Market Regime & Online Learning Intelligence */}
          <div className="glass-panel p-5 shrink-0 mb-4">
            <h2 className="text-xs font-semibold uppercase text-white/50 mb-3 tracking-wider flex items-center justify-between">
              <span>Market Regime</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                marketRegime.regime === "TRENDING" ? "bg-brand-green/20 text-brand-green border border-brand-green/30" :
                marketRegime.regime === "RANGING/CHOPPY" ? "bg-amber-500/20 text-amber-400 border border-amber-500/30" :
                "bg-blue-500/20 text-blue-400 border border-blue-500/30"
              }`}>
                {marketRegime.regime}
              </span>
            </h2>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between items-center py-1 border-b border-white/5">
                <span className="text-white/60">ADX Trend (14):</span>
                <span className="font-mono font-bold text-white">{marketRegime.adx}</span>
              </div>
              <div className="flex justify-between items-center py-1 border-b border-white/5">
                <span className="text-white/60">Auto Micro-Retrain:</span>
                <span className={onlineLearning.enabled ? "text-brand-green font-semibold" : "text-white/40"}>
                  {onlineLearning.enabled ? "Active (Hourly)" : "Disabled"}
                </span>
              </div>
              {onlineLearning.last_retrain && (
                <div className="flex justify-between items-center py-1 text-[11px] text-white/40">
                  <span>Last Micro Retrain:</span>
                  <span className="font-mono">{onlineLearning.last_retrain}</span>
                </div>
              )}
            </div>
          </div>
          
        </div>

        {/* Right Column: Chart */}
        <div className="flex-1 glass-panel p-1 flex flex-col min-h-[400px]">
           <TradingChart isLive={isLive} />
        </div>

      </div>
    </div>
  );
}

function MetricRow({ label, value, color = "text-white" }: { label: string, value: string | number, color?: string }) {
  return (
    <div className="flex justify-between items-center py-2 border-b border-white/5 last:border-0">
      <span className="text-sm text-white/60 font-medium">{label}</span>
      <span className={`text-sm font-bold ${color}`}>{value}</span>
    </div>
  );
}
