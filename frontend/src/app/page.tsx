"use client";

import { useState, useEffect } from "react";
import { Power, Activity } from "lucide-react";
import dynamic from "next/dynamic";
import { getApiBaseUrl } from "@/config";

// Dynamically import TradingChart to avoid SSR issues with canvas
const TradingChart = dynamic(() => import("@/components/TradingChart"), { ssr: false });
import NewsCountdown, { MacroEvent } from "@/components/NewsCountdown";

export default function Home() {
  const [isLive, setIsLive] = useState(false);
  const [selectedMode, setSelectedMode] = useState("auto");
  const [marketRegime, setMarketRegime] = useState<{ adx: number; regime: string }>({ adx: 0, regime: "DETECTING..." });
  const [onlineLearning, setOnlineLearning] = useState<{ enabled: boolean; last_retrain: string | null }>({ enabled: true, last_retrain: null });
  const [nextNews, setNextNews] = useState<MacroEvent | null>(null);

  useEffect(() => {
    const fetchState = () => {
      fetch(`${getApiBaseUrl()}/api/state`)
        .then(res => res.json())
        .then(data => {
          setIsLive(data.is_live);
          if (data.market_regime) setMarketRegime(data.market_regime);
          if (data.online_learning) setOnlineLearning(data.online_learning);
          if (data.next_high_impact_news !== undefined) setNextNews(data.next_high_impact_news);
        })
        .catch(err => console.error("Backend offline", err));
    };
    fetchState();
    const interval = setInterval(fetchState, 3000);
    return () => clearInterval(interval);
  }, []);

  const toggleLive = async () => {
    try {
      if (!isLive && selectedMode !== "auto") {
         await fetch(`${getApiBaseUrl()}/api/strategies/force_live`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mode: selectedMode.replace("force_", "") })
         });
      }
      const res = await fetch(`${getApiBaseUrl()}/api/state/toggle`, { method: "POST" });
      const data = await res.json();
      setIsLive(data.is_live);
    } catch (err) {
      console.error("Failed to toggle state", err);
    }
  };

  return (
    <div className="p-3 sm:p-4 md:p-6 flex flex-col gap-4 md:gap-5 min-h-full">
      
      {/* Top Row: All Widgets Aligned Left-to-Right Above the Candlestick Chart */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 shrink-0">
        
        {/* Widget 1: Macro Bridge: High Impact News Countdown */}
        <div className="h-full">
          <NewsCountdown initialEvent={nextNews} />
        </div>

        {/* Widget 2: AI Bot State & Execution Mode */}
        <div className="glass-panel p-4 sm:p-5 flex flex-col justify-between relative overflow-hidden h-full">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-bold uppercase text-white/50 tracking-wider">AI Bot State</h2>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
              isLive ? "bg-brand-green/20 text-brand-green border border-brand-green/40 animate-pulse" : "bg-white/10 text-white/40"
            }`}>
              {isLive ? "ACTIVE" : "PAUSED"}
            </span>
          </div>

          <div className="my-auto py-2 flex flex-col gap-2">
            {!isLive && (
              <select 
                value={selectedMode} 
                onChange={(e) => setSelectedMode(e.target.value)}
                className="w-full bg-black/40 border border-white/10 text-white text-xs rounded-lg p-2 focus:ring-1 focus:ring-brand-green outline-none"
              >
                <option value="auto">Auto (Strict OOS Validation)</option>
                <option value="force_normal">Forced Live: Normal Mode</option>
                <option value="force_runner">Forced Live: Runner Mode</option>
              </select>
            )}

            <button 
              onClick={toggleLive}
              className={`flex items-center justify-center gap-2.5 py-3 px-4 rounded-xl transition-all duration-300 w-full font-black text-base sm:text-lg tracking-widest cursor-pointer ${
                isLive 
                  ? 'bg-brand-green/20 text-brand-green border border-brand-green/50 glow-green hover:bg-brand-green/30' 
                  : 'bg-white/10 text-white hover:bg-brand-green/20 hover:text-brand-green hover:border-brand-green/30 border border-transparent'
              }`}
            >
              <Power size={20} className={isLive ? 'animate-pulse' : ''} />
              <span>{isLive ? 'LIVE' : 'START BOT'}</span>
            </button>
          </div>

          <p className="text-[11px] text-white/40 font-medium text-center mt-1">
            {isLive ? 'Active Since: Just now' : 'System is currently paused'}
          </p>
        </div>

        {/* Widget 3: Market Regime & Online Learning Intelligence */}
        <div className="glass-panel p-4 sm:p-5 flex flex-col justify-between h-full">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold uppercase text-white/50 tracking-wider">Market Regime</h2>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
              marketRegime.regime === "TRENDING" ? "bg-brand-green/20 text-brand-green border border-brand-green/30" :
              marketRegime.regime === "RANGING/CHOPPY" ? "bg-amber-500/20 text-amber-400 border border-amber-500/30" :
              "bg-blue-500/20 text-blue-400 border border-blue-500/30"
            }`}>
              {marketRegime.regime}
            </span>
          </div>

          <div className="space-y-2 text-xs my-auto">
            <div className="flex justify-between items-center py-1.5 border-b border-white/5">
              <span className="text-white/60">ADX Trend (14):</span>
              <span className="font-mono font-bold text-white text-sm">{marketRegime.adx}</span>
            </div>
            <div className="flex justify-between items-center py-1.5 border-b border-white/5">
              <span className="text-white/60">Auto Micro-Retrain:</span>
              <span className={onlineLearning.enabled ? "text-brand-green font-semibold" : "text-white/40"}>
                {onlineLearning.enabled ? "Active (Hourly)" : "Disabled"}
              </span>
            </div>
          </div>

          <div className="pt-2 text-[10px] text-white/40 flex justify-between border-t border-white/5 mt-2">
            <span>Last Retrain:</span>
            <span className="font-mono">{onlineLearning.last_retrain || "No retrain yet"}</span>
          </div>
        </div>

      </div>

      {/* Bottom: Full-Width Candlestick Chart */}
      <div className="flex-1 glass-panel p-1.5 sm:p-2 flex flex-col min-h-[460px] md:min-h-[500px]">
        <TradingChart isLive={isLive} />
      </div>

    </div>
  );
}

