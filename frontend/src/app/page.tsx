"use client";

import { useState, useEffect } from "react";
import { Power } from "lucide-react";
import dynamic from "next/dynamic";

// Dynamically import TradingChart to avoid SSR issues with canvas
const TradingChart = dynamic(() => import("@/components/TradingChart"), { ssr: false });

export default function Home() {
  const [isLive, setIsLive] = useState(false);
  const [metrics, setMetrics] = useState({
    win_rate: 0,
    total_trades: 0,
    avg_profit: 0,
    max_drawdown: 0
  });

  useEffect(() => {
    fetch("http://localhost:8000/api/state")
      .then(res => res.json())
      .then(data => {
        setIsLive(data.is_live);
        setMetrics(data.performance);
      })
      .catch(err => console.error("Backend offline", err));
  }, []);

  const toggleLive = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/state/toggle", { method: "POST" });
      const data = await res.json();
      setIsLive(data.is_live);
    } catch (err) {
      console.error("Failed to toggle state", err);
    }
  };

  return (
    <div className="p-6 flex flex-col lg:flex-row gap-6">
      
      {/* Left Column: Stats & Controls */}
      <div className="w-full lg:w-80 flex flex-col gap-6 shrink-0">
        
        {/* AI Bot State */}
        <div className="glass-panel p-6 flex flex-col items-center justify-center relative overflow-hidden">
          <h2 className="text-xs font-semibold uppercase text-white/50 mb-6 tracking-wider w-full text-left">AI Bot State</h2>
          <button 
            onClick={toggleLive}
            className={`relative flex items-center justify-center gap-3 px-8 py-4 rounded-2xl transition-all duration-300 w-full ${isLive ? 'bg-brand-green/20 text-brand-green glow-green' : 'bg-white/5 text-white/40'}`}
          >
            <Power size={24} className={isLive ? 'animate-pulse' : ''} />
            <span className="font-black text-2xl tracking-widest">{isLive ? 'LIVE' : 'OFFLINE'}</span>
          </button>
          <p className="text-xs text-white/40 mt-6 font-medium">
            {isLive ? 'Active Since: Just now' : 'System is currently paused'}
          </p>
        </div>

        {/* Performance Metrics */}
        <div className="glass-panel p-6">
          <h2 className="text-xs font-semibold uppercase text-white/50 mb-6 tracking-wider">Performance Metrics</h2>
          <div className="flex justify-center mb-8">
            <div className="w-32 h-32 rounded-full border-4 border-brand-green flex flex-col items-center justify-center relative glow-green">
              <span className="text-[10px] text-white/50 font-bold uppercase mb-1">Win Rate</span>
              <span className="text-3xl font-black text-white">{metrics.win_rate}%</span>
            </div>
          </div>
          <div className="space-y-4">
            <MetricRow label="Total Trades" value={metrics.total_trades} />
            <MetricRow label="Avg Profit" value={`${metrics.avg_profit}%`} color="text-brand-green" />
            <MetricRow label="Max Drawdown" value={`${metrics.max_drawdown}%`} color="text-brand-red" />
          </div>
        </div>
        
      </div>

      {/* Right Column: Chart */}
      <div className="flex-1 glass-panel p-1 flex flex-col h-[600px] lg:h-auto">
         <TradingChart isLive={isLive} />
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
