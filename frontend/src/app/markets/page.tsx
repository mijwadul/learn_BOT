"use client";

import { useState, useEffect } from "react";
import {
  Globe,
  Clock,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  AlertTriangle,
  Zap,
  Calendar,
  Layers,
  Activity,
  ShieldCheck,
} from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";

interface ScreenerAsset {
  symbol: string;
  name: string;
  category: string;
  correlation: number;
  price: number;
  bid: number;
  ask: number;
  spread_pts: number;
  change_24h: number;
  atr_14: number;
  trend: "BULLISH" | "BEARISH" | "NEUTRAL";
  volatility: "HIGH" | "MODERATE" | "LOW" | "NORMAL";
}

interface MacroEvent {
  id?: number;
  time: string;
  currency: string;
  event: string;
  impact: string;
  forecast?: string;
  previous?: string;
  actual?: string;
}

export default function MarketsPage() {
  const toast = useToast();
  const [currentTimeUTC, setCurrentTimeUTC] = useState<string>("");
  const [currentTimeLocal, setCurrentTimeLocal] = useState<string>("");
  const [screener, setScreener] = useState<ScreenerAsset[]>([]);
  const [macroEvents, setMacroEvents] = useState<MacroEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);

  // Update real-time world clocks (24-hour format)
  useEffect(() => {
    const pad = (n: number) => String(n).padStart(2, "0");
    const updateTime = () => {
      const now = new Date();
      setCurrentTimeUTC(now.toISOString().substring(11, 19) + " UTC");
      const localH = pad(now.getHours());
      const localM = pad(now.getMinutes());
      const localS = pad(now.getSeconds());
      setCurrentTimeLocal(`${localH}:${localM}:${localS}`);
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Fetch screener and macro events
  const fetchMarketData = async () => {
    try {
      const [screenerRes, macroRes] = await Promise.all([
        fetch(`${getApiBaseUrl()}/api/market/screener`),
        fetch(`${getApiBaseUrl()}/api/macro/events`),
      ]);

      if (screenerRes.ok) {
        const scData = await screenerRes.json();
        if (scData.status === "success" && scData.screener) {
          setScreener(scData.screener);
        }
      }

      if (macroRes.ok) {
        const mData = await macroRes.json();
        if (mData.status === "success" && mData.events) {
          setMacroEvents(mData.events);
        }
      }
    } catch (err) {
      console.error("Failed to fetch market screener data", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchMarketData();
    const interval = setInterval(fetchMarketData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleManualSync = async () => {
    setIsSyncing(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/macro/sync`, { method: "POST" });
      const data = await res.json();
      if (data.status === "success") {
        toast.success(
          `Successfully synchronized ${data.synced_count ?? 0} macro events from MetaTrader 5.`,
          "Calendar Synced"
        );
        fetchMarketData();
      } else {
        toast.error(
          data.message || "Failed to trigger macro synchronization.",
          "Sync Warning"
        );
      }
    } catch (err: any) {
      toast.error(
        err?.message || "Could not connect to backend server.",
        "Sync Failed"
      );
    } finally {
      setIsSyncing(false);
    }
  };

  // Determine active sessions in UTC
  const currentHourUTC = new Date().getUTCHours();
  const currentMinuteUTC = new Date().getUTCMinutes();
  const utcDecimal = currentHourUTC + currentMinuteUTC / 60;

  const isTokyoActive = utcDecimal >= 0 && utcDecimal < 9;
  const isLondonActive = utcDecimal >= 7 && utcDecimal < 16;
  const isNYActive = utcDecimal >= 12 && utcDecimal < 21;
  const isOverlapActive = utcDecimal >= 12 && utcDecimal < 16;

  return (
    <div className="p-3 sm:p-4 md:p-6 min-h-full flex flex-col gap-6">
      {/* Header with Title and Live Clocks */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-widest flex items-center gap-2 sm:gap-3">
            <Globe className="text-brand-green" /> MACRO & MARKET SCREENER
          </h1>
          <p className="text-white/50 text-xs sm:text-sm mt-1">
            Global Inter-Market Correlation, World Session Clocks & Economic Catalysts
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-black/40 border border-white/10 font-mono text-xs text-white/80 shadow-inner">
            <Clock size={14} className="text-brand-green animate-pulse" />
            <span className="font-bold text-white">{currentTimeUTC || "--:--:-- UTC"}</span>
            <span className="text-white/30">|</span>
            <span className="text-white/60">{currentTimeLocal || "--:--:--"}</span>
          </div>

          <button
            onClick={handleManualSync}
            disabled={isSyncing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-white/80 hover:text-white border border-white/10 text-xs font-bold transition-all disabled:opacity-50 cursor-pointer"
            title="Force sync MT5 economic calendar"
          >
            <RefreshCw size={13} className={isSyncing ? "animate-spin text-brand-green" : ""} />
            <span>{isSyncing ? "Syncing..." : "Sync Calendar"}</span>
          </button>
        </div>
      </div>

      {/* World Trading Session Clocks */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {/* Tokyo */}
        <div
          className={`p-3.5 rounded-xl border transition-all relative overflow-hidden ${
            isTokyoActive
              ? "bg-emerald-950/20 border-emerald-500/40 shadow-lg shadow-emerald-500/5"
              : "bg-black/20 border-white/5 opacity-60"
          }`}
        >
          <div className="flex justify-between items-start mb-2">
            <div>
              <span className="text-[10px] font-mono tracking-wider uppercase text-white/50">Asian Session</span>
              <h3 className="text-sm font-bold text-white flex items-center gap-1.5">Tokyo (TSE)</h3>
            </div>
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                isTokyoActive ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : "bg-white/5 text-white/40"
              }`}
            >
              {isTokyoActive ? "ACTIVE" : "CLOSED"}
            </span>
          </div>
          <div className="text-xs font-mono text-white/60">00:00 - 09:00 UTC</div>
        </div>

        {/* London */}
        <div
          className={`p-3.5 rounded-xl border transition-all relative overflow-hidden ${
            isLondonActive
              ? "bg-blue-950/20 border-blue-500/40 shadow-lg shadow-blue-500/5"
              : "bg-black/20 border-white/5 opacity-60"
          }`}
        >
          <div className="flex justify-between items-start mb-2">
            <div>
              <span className="text-[10px] font-mono tracking-wider uppercase text-white/50">European Session</span>
              <h3 className="text-sm font-bold text-white flex items-center gap-1.5">London (LSE)</h3>
            </div>
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                isLondonActive ? "bg-blue-500/20 text-blue-400 border border-blue-500/30" : "bg-white/5 text-white/40"
              }`}
            >
              {isLondonActive ? "ACTIVE" : "CLOSED"}
            </span>
          </div>
          <div className="text-xs font-mono text-white/60">07:00 - 16:00 UTC</div>
        </div>

        {/* New York */}
        <div
          className={`p-3.5 rounded-xl border transition-all relative overflow-hidden ${
            isNYActive
              ? "bg-purple-950/20 border-purple-500/40 shadow-lg shadow-purple-500/5"
              : "bg-black/20 border-white/5 opacity-60"
          }`}
        >
          <div className="flex justify-between items-start mb-2">
            <div>
              <span className="text-[10px] font-mono tracking-wider uppercase text-white/50">US Session</span>
              <h3 className="text-sm font-bold text-white flex items-center gap-1.5">New York (NYSE)</h3>
            </div>
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                isNYActive ? "bg-purple-500/20 text-purple-400 border border-purple-500/30" : "bg-white/5 text-white/40"
              }`}
            >
              {isNYActive ? "ACTIVE" : "CLOSED"}
            </span>
          </div>
          <div className="text-xs font-mono text-white/60">12:00 - 21:00 UTC</div>
        </div>

        {/* Overlap */}
        <div
          className={`p-3.5 rounded-xl border transition-all relative overflow-hidden ${
            isOverlapActive
              ? "bg-amber-950/30 border-amber-500/50 shadow-lg shadow-amber-500/10 ring-1 ring-amber-500/30"
              : "bg-black/20 border-white/5 opacity-60"
          }`}
        >
          <div className="flex justify-between items-start mb-2">
            <div>
              <span className="text-[10px] font-mono tracking-wider uppercase text-amber-400 font-bold flex items-center gap-1">
                <Zap size={11} /> Overlap Peak
              </span>
              <h3 className="text-sm font-bold text-white">London - NY</h3>
            </div>
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold ${
                isOverlapActive ? "bg-amber-500/30 text-amber-300 border border-amber-500/40 animate-pulse" : "bg-white/5 text-white/40"
              }`}
            >
              {isOverlapActive ? "PEAK VOL" : "STANDBY"}
            </span>
          </div>
          <div className="text-xs font-mono text-white/60">12:00 - 16:00 UTC</div>
        </div>
      </div>

      {/* Multi-Asset & Gold Correlation Screener Table */}
      <div className="glass-panel p-4 sm:p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between border-b border-white/5 pb-3">
          <div className="flex items-center gap-2">
            <Layers size={18} className="text-brand-green" />
            <h2 className="text-base sm:text-lg font-bold text-white">Inter-Market Correlation Matrix</h2>
          </div>
          <span className="text-[11px] font-mono text-white/40">Anchor Asset: XAUUSD (Gold)</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-white/10 text-white/40 font-mono uppercase text-[10px]">
                <th className="py-2.5 px-3">Asset</th>
                <th className="py-2.5 px-3">Class</th>
                <th className="py-2.5 px-3 text-right">Gold Corr</th>
                <th className="py-2.5 px-3 text-right">Price</th>
                <th className="py-2.5 px-3 text-right">Spread</th>
                <th className="py-2.5 px-3 text-right">24h Chg</th>
                <th className="py-2.5 px-3 text-center">ATR (14)</th>
                <th className="py-2.5 px-3 text-center">Regime Trend</th>
                <th className="py-2.5 px-3 text-center">Volatility</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 font-mono">
              {screener.map((item) => {
                const isPositive = item.change_24h >= 0;
                const isGold = item.symbol === "XAUUSD";
                return (
                  <tr key={item.symbol} className={`hover:bg-white/[0.02] transition-colors ${isGold ? "bg-white/[0.02]" : ""}`}>
                    <td className="py-3 px-3">
                      <div className="flex items-center gap-2">
                        <span className={`font-bold text-sm ${isGold ? "text-amber-400" : "text-white"}`}>{item.symbol}</span>
                        {isGold && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30">
                            CORE
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-white/40">{item.name}</div>
                    </td>

                    <td className="py-3 px-3 text-white/60 text-[11px]">{item.category}</td>

                    <td className="py-3 px-3 text-right">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[11px] font-bold ${
                          item.correlation > 0.5
                            ? "bg-emerald-500/20 text-emerald-400"
                            : item.correlation < -0.5
                            ? "bg-purple-500/20 text-purple-400"
                            : "bg-white/5 text-white/60"
                        }`}
                      >
                        {item.correlation > 0 ? `+${item.correlation.toFixed(2)}` : item.correlation.toFixed(2)}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-right font-bold text-white text-sm">
                      {item.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                    </td>

                    <td className="py-3 px-3 text-right text-white/70">
                      {item.spread_pts} <span className="text-[10px] text-white/40">pts</span>
                    </td>

                    <td className="py-3 px-3 text-right">
                      <span className={`inline-flex items-center gap-0.5 font-bold ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                        {isPositive ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                        {isPositive ? `+${item.change_24h.toFixed(2)}%` : `${item.change_24h.toFixed(2)}%`}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-center text-white/70">{item.atr_14}</td>

                    <td className="py-3 px-3 text-center">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          item.trend === "BULLISH"
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                            : item.trend === "BEARISH"
                            ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                            : "bg-white/10 text-white/50 border border-white/10"
                        }`}
                      >
                        {item.trend}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-center">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          item.volatility === "HIGH"
                            ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                            : item.volatility === "MODERATE"
                            ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                            : "bg-white/5 text-white/40"
                        }`}
                      >
                        {item.volatility}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bottom Grid: Macro Economic News Schedule & Institutional Correlation Insight */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Upcoming High Impact Economic Events */}
        <div className="lg:col-span-2 glass-panel p-4 sm:p-5 flex flex-col gap-3">
          <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
            <div className="flex items-center gap-2">
              <Calendar size={17} className="text-brand-green" />
              <h2 className="text-base font-bold text-white">Upcoming High Impact News Catalysts</h2>
            </div>
            <span className="text-[10px] font-mono text-white/40">MT5 Economic Bridge</span>
          </div>

          {macroEvents.length === 0 ? (
            <div className="py-8 text-center text-white/40 text-xs">
              No upcoming high impact news events logged for today.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-white/10 text-white/40 font-mono uppercase text-[10px]">
                    <th className="py-2 px-2">Time</th>
                    <th className="py-2 px-2">Currency</th>
                    <th className="py-2 px-2">Impact</th>
                    <th className="py-2 px-2">Event</th>
                    <th className="py-2 px-2 text-right">Forecast</th>
                    <th className="py-2 px-2 text-right">Previous</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 font-mono text-[11px]">
                  {macroEvents.slice(0, 6).map((ev, idx) => (
                    <tr key={ev.id ?? idx} className="hover:bg-white/[0.02]">
                      <td className="py-2.5 px-2 text-white/70 whitespace-nowrap">{ev.time}</td>
                      <td className="py-2.5 px-2 font-bold text-white">{ev.currency}</td>
                      <td className="py-2.5 px-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                            ev.impact === "HIGH"
                              ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                              : ev.impact === "MEDIUM"
                              ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                              : "bg-white/5 text-white/40"
                          }`}
                        >
                          {ev.impact}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-white/90 max-w-[200px] truncate">{ev.event}</td>
                      <td className="py-2.5 px-2 text-right text-white/60">{ev.forecast || "--"}</td>
                      <td className="py-2.5 px-2 text-right text-white/40">{ev.previous || "--"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Institutional Macro Bias & Risk Protocol */}
        <div className="glass-panel p-4 sm:p-5 flex flex-col justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 border-b border-white/5 pb-2.5 mb-3">
              <ShieldCheck size={17} className="text-emerald-400" />
              <h2 className="text-base font-bold text-white">Institutional Macro Bias</h2>
            </div>
            <p className="text-xs text-white/60 leading-relaxed">
              Gold spot (XAUUSD) exhibits a strong inverse correlation with the US Dollar Index (<span className="text-purple-400 font-bold">-0.84</span>) and US 10-Year Yields (<span className="text-purple-400 font-bold">-0.72</span>).
            </p>
            <div className="mt-3.5 space-y-2 text-xs">
              <div className="flex justify-between items-center py-1.5 border-b border-white/5">
                <span className="text-white/50">News Blackout Window:</span>
                <span className="font-mono font-bold text-amber-400">&plusmn;15 Minutes</span>
              </div>
              <div className="flex justify-between items-center py-1.5 border-b border-white/5">
                <span className="text-white/50">Auto Break-Even on News:</span>
                <span className="font-mono font-bold text-emerald-400">Armed</span>
              </div>
              <div className="flex justify-between items-center py-1.5 border-b border-white/5">
                <span className="text-white/50">Max Spread Circuit:</span>
                <span className="font-mono font-bold text-white">45 pts</span>
              </div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-black/30 border border-white/10 text-[11px] text-white/50 leading-normal">
            <span className="text-amber-400 font-bold block mb-1">Safety Rule #3:</span>
            Execution is hard-paused when active spread exceeds the dynamic tolerance or during High-Impact USD news events.
          </div>
        </div>
      </div>
    </div>
  );
}
