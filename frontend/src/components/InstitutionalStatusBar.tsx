"use client";

import React, { useEffect, useState } from "react";
import { Activity, ShieldAlert, Cpu, Radio, Clock, AlertTriangle } from "lucide-react";
import { getApiBaseUrl } from "@/config";

interface StatusBarData {
  mt5_connected: boolean;
  active_symbol: string;
  supervisor_state: string;
  portfolio: {
    value: number;
    equity: number;
  };
  market_regime: {
    adx: number;
    regime: string;
  };
  next_high_impact_news?: {
    event_name: string;
    currency: string;
    minutes_remaining: number;
    is_imminent: boolean;
  };
}

export function InstitutionalStatusBar() {
  const [data, setData] = useState<StatusBarData | null>(null);
  const [latency, setLatency] = useState<number>(14);

  useEffect(() => {
    let isMounted = true;

    const fetchStatus = async () => {
      const startTime = performance.now();
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/state`);
        const measuredLatency = Math.round(performance.now() - startTime);
        if (res.ok && isMounted) {
          const json = await res.json();
          setData(json);
          setLatency(measuredLatency);
        }
      } catch (e) {
        if (isMounted) setLatency(999);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 4000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  const balance = data?.portfolio?.value || 10000;
  const equity = data?.portfolio?.equity || balance;
  const ddVal = balance > 0 ? Math.max(0, ((balance - equity) / balance) * 100) : 0;
  const isDdWarning = ddVal >= 15.0;

  const regimeName = data?.market_regime?.regime || "UNKNOWN";
  const adxVal = data?.market_regime?.adx || 0;
  const nextNews = data?.next_high_impact_news;

  return (
    <div className="w-full bg-[#070b0a]/90 border-b border-white/10 px-4 py-2 flex flex-wrap items-center justify-between gap-3 text-xs backdrop-blur-md z-30 select-none">
      {/* Left side: MT5 Terminal & Server status */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${data?.mt5_connected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"}`} />
          <span className="font-bold text-white/90">MT5:</span>
          <span className={data?.mt5_connected ? "text-emerald-400 font-semibold font-mono tabular-nums" : "text-rose-400 font-semibold"}>
            {data?.mt5_connected ? `Connected (${latency}ms)` : "Disconnected"}
          </span>
        </div>

        <div className="h-3 w-px bg-white/10 hidden sm:block" />

        <div className="flex items-center gap-1.5 text-white/80">
          <Radio className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-semibold text-white/50">Symbol:</span>
          <span className="font-bold text-cyan-300 font-mono">{data?.active_symbol || "XAUUSD"}</span>
        </div>

        <div className="h-3 w-px bg-white/10 hidden sm:block" />

        {/* Market Regime */}
        <div className="flex items-center gap-1.5">
          <Cpu className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-semibold text-white/50">Regime:</span>
          <span className={`font-bold px-1.5 py-0.5 rounded text-[10px] tracking-wider font-mono tabular-nums ${
            regimeName === "TRENDING" 
              ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30" 
              : regimeName === "RANGING/CHOPPY"
              ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
              : "bg-white/10 text-white/70"
          }`}>
            {regimeName} (ADX {adxVal.toFixed(1)})
          </span>
        </div>
      </div>

      {/* Right side: Drawdown, News Countdown, Bot State */}
      <div className="flex items-center gap-4 flex-wrap ml-auto">
        {/* Drawdown Risk Gauge */}
        <div className="flex items-center gap-1.5">
          <ShieldAlert className={`w-3.5 h-3.5 ${isDdWarning ? "text-rose-400 animate-bounce" : "text-emerald-400"}`} />
          <span className="font-semibold text-white/50">DD:</span>
          <span className={`font-bold font-mono tabular-nums ${isDdWarning ? "text-rose-400" : "text-emerald-400"}`}>
            {ddVal.toFixed(1)}% / 30%
          </span>
        </div>

        <div className="h-3 w-px bg-white/10 hidden sm:block" />

        {/* High Impact Macro News Countdown */}
        {nextNews ? (
          <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-lg border ${
            nextNews.is_imminent 
              ? "bg-rose-500/20 border-rose-500/40 text-rose-300 animate-pulse font-bold" 
              : "bg-white/5 border-white/10 text-white/80"
          }`}>
            <Clock className="w-3 h-3 text-amber-400 shrink-0" />
            <span className="truncate max-w-[140px] sm:max-w-none text-[11px] font-mono tabular-nums">
              {nextNews.currency}: {nextNews.event_name} ({nextNews.minutes_remaining > 0 ? `${nextNews.minutes_remaining}m` : "LIVE"})
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-1 text-white/40 text-[11px]">
            <Clock className="w-3 h-3" />
            <span>No Imminent News</span>
          </div>
        )}

        <div className="h-3 w-px bg-white/10 hidden sm:block" />

        {/* Engine Status */}
        <div className="flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-brand-green" />
          <span className="font-semibold text-white/50">State:</span>
          <span className="font-bold text-brand-green uppercase tracking-wider text-[11px]">
            {data?.supervisor_state || "IDLE"}
          </span>
        </div>
      </div>
    </div>
  );
}
