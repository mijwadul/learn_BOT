"use client";

import React, { useState, useEffect } from "react";
import { AlertTriangle, Clock, Calendar, Zap, ShieldAlert, CheckCircle2 } from "lucide-react";
import { getApiBaseUrl } from "@/config";

export interface MacroEvent {
  id?: number;
  event_id?: string;
  event_name: string;
  country?: string;
  currency: string;
  impact: string;
  date: string;
  estimate?: number | null;
  previous?: number | null;
  actual?: number | null;
  seconds_remaining?: number;
  minutes_remaining?: number;
  is_imminent?: boolean;
}

interface NewsCountdownProps {
  initialEvent?: MacroEvent | null;
}

export default function NewsCountdown({ initialEvent }: NewsCountdownProps) {
  const [event, setEvent] = useState<MacroEvent | null>(initialEvent || null);
  const [timeLeft, setTimeLeft] = useState<{ hours: number; minutes: number; seconds: number; isNegative: boolean }>({
    hours: 0,
    minutes: 0,
    seconds: 0,
    isNegative: false,
  });

  // Fetch / Refresh event data from API
  useEffect(() => {
    const fetchNextEvent = () => {
      fetch(`${getApiBaseUrl()}/api/macro/next-event`)
        .then((res) => res.json())
        .then((data) => {
          if (data.status === "success") {
            setEvent(data.event);
          }
        })
        .catch((err) => console.debug("Error fetching next macro event:", err));
    };

    if (!initialEvent) {
      fetchNextEvent();
    }
    const pollInterval = setInterval(fetchNextEvent, 15000); // refresh every 15s
    return () => clearInterval(pollInterval);
  }, [initialEvent]);

  // Real-time ticking countdown timer (every 1 second)
  useEffect(() => {
    if (!event || !event.date) return;

    const calculateTime = () => {
      const targetTime = new Date(event.date).getTime();
      const now = new Date().getTime();
      const diffMs = targetTime - now;

      const isNegative = diffMs < 0;
      const totalSec = Math.abs(Math.floor(diffMs / 1000));

      const hours = Math.floor(totalSec / 3600);
      const minutes = Math.floor((totalSec % 3600) / 60);
      const seconds = totalSec % 60;

      setTimeLeft({ hours, minutes, seconds, isNegative });
    };

    calculateTime();
    const timer = setInterval(calculateTime, 1000);
    return () => clearInterval(timer);
  }, [event]);

  // Format number to 2 digits
  const pad = (n: number) => String(n).padStart(2, "0");

  if (!event) {
    return (
      <div className="glass-panel p-4 shrink-0 border border-white/5 bg-gradient-to-br from-white/[0.03] to-transparent">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-brand-green animate-pulse" />
            <h3 className="text-xs font-semibold uppercase text-white/50 tracking-wider">
              Macro Intelligence
            </h3>
          </div>
          <span className="text-[10px] text-brand-green/80 flex items-center gap-1 font-mono">
            <CheckCircle2 size={12} /> Clear Window
          </span>
        </div>
        <p className="text-xs text-white/40 mt-2">
          No High Impact news detected in the near schedule. Safe market environment.
        </p>
      </div>
    );
  }

  // Status and Urgency Calculation
  const totalMinutesRemaining = (timeLeft.hours * 60) + timeLeft.minutes;
  const isImminent = !timeLeft.isNegative && totalMinutesRemaining <= 30; // <= 30 min
  const isOngoing = timeLeft.isNegative && totalMinutesRemaining <= 15; // 0 to 15 min past

  return (
    <div
      className={`glass-panel p-4 shrink-0 transition-all duration-300 relative overflow-hidden border ${
        isOngoing
          ? "border-red-500/50 bg-red-950/20 shadow-[0_0_25px_rgba(239,68,68,0.2)]"
          : isImminent
          ? "border-amber-500/40 bg-amber-950/20 shadow-[0_0_20px_rgba(245,158,11,0.15)]"
          : "border-white/10 hover:border-white/20"
      }`}
    >
      {/* Subtle top indicator bar */}
      <div
        className={`absolute top-0 left-0 right-0 h-1 ${
          isOngoing ? "bg-red-500 animate-pulse" : isImminent ? "bg-amber-400 animate-pulse" : "bg-brand-green"
        }`}
      />

      {/* Header with Title and Currency Badge */}
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2">
          {isOngoing ? (
            <ShieldAlert size={15} className="text-red-400 animate-bounce" />
          ) : isImminent ? (
            <AlertTriangle size={15} className="text-amber-400 animate-pulse" />
          ) : (
            <Clock size={15} className="text-brand-green" />
          )}
          <h3 className="text-xs font-bold uppercase tracking-wider text-white/70">
            High Impact News Countdown
          </h3>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="px-2 py-0.5 rounded text-[10px] font-extrabold font-mono bg-white/10 text-white border border-white/10">
            {event.currency || "USD"}
          </span>
          <span className="px-2 py-0.5 rounded text-[10px] font-extrabold uppercase bg-red-500/20 text-red-400 border border-red-500/30">
            HIGH IMPACT
          </span>
        </div>
      </div>

      {/* Event Name */}
      <div className="mb-3">
        <h4 className="text-sm font-bold text-white tracking-wide truncate" title={event.event_name}>
          {event.event_name}
        </h4>
        <div className="flex items-center gap-3 text-[11px] text-white/40 mt-0.5">
          <span className="flex items-center gap-1">
            <Calendar size={11} />
            {new Date(event.date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })} WIB
          </span>
          {event.country && <span>Country: {event.country}</span>}
        </div>
      </div>

      {/* Large Live Digital Countdown Box */}
      <div className="bg-black/50 border border-white/10 rounded-xl p-3 flex items-center justify-between mb-3">
        <span className="text-[11px] uppercase tracking-wider text-white/50 font-semibold flex items-center gap-1.5">
          <Zap size={13} className={isImminent || isOngoing ? "text-amber-400 animate-pulse" : "text-brand-green"} />
          {isOngoing ? "Released (Volatile):" : "Time To Impact:"}
        </span>

        {/* Digital Clock Display */}
        <div className="flex items-center gap-1 font-mono font-black text-lg sm:text-xl tracking-wider">
          <div className="bg-white/5 px-2 py-0.5 rounded border border-white/5 text-white">
            {pad(timeLeft.hours)}<span className="text-[10px] text-white/40 ml-0.5">h</span>
          </div>
          <span className="text-white/40 animate-pulse">:</span>
          <div className={`px-2 py-0.5 rounded border ${
            isOngoing
              ? "bg-red-500/20 text-red-400 border-red-500/30 animate-pulse"
              : isImminent
              ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
              : "bg-white/5 text-brand-green border-white/5"
          }`}>
            {pad(timeLeft.minutes)}<span className="text-[10px] opacity-60 ml-0.5">m</span>
          </div>
          <span className="text-white/40 animate-pulse">:</span>
          <div className={`px-2 py-0.5 rounded border ${
            isOngoing
              ? "bg-red-500/20 text-red-400 border-red-500/30 animate-pulse"
              : isImminent
              ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
              : "bg-white/5 text-white border-white/5"
          }`}>
            {pad(timeLeft.seconds)}<span className="text-[10px] opacity-60 ml-0.5">s</span>
          </div>
        </div>
      </div>

      {/* Forecast / Previous Data Grid */}
      <div className="grid grid-cols-3 gap-2 text-center text-xs bg-white/[0.02] p-2 rounded-lg border border-white/5 font-mono">
        <div>
          <span className="text-[10px] text-white/40 block">Forecast</span>
          <span className="font-bold text-white">
            {event.estimate !== null && event.estimate !== undefined ? event.estimate : "-"}
          </span>
        </div>
        <div>
          <span className="text-[10px] text-white/40 block">Previous</span>
          <span className="font-bold text-white/70">
            {event.previous !== null && event.previous !== undefined ? event.previous : "-"}
          </span>
        </div>
        <div>
          <span className="text-[10px] text-white/40 block">Actual</span>
          <span className={`font-bold ${event.actual !== null && event.actual !== undefined ? "text-brand-green" : "text-white/30"}`}>
            {event.actual !== null && event.actual !== undefined ? event.actual : "Pending"}
          </span>
        </div>
      </div>

      {/* Circuit Breaker Status Alert */}
      {isImminent && (
        <div className="mt-2.5 flex items-center gap-1.5 text-[11px] text-amber-300 bg-amber-500/10 border border-amber-500/20 px-2.5 py-1.5 rounded-lg">
          <AlertTriangle size={12} className="shrink-0 animate-pulse" />
          <span>Macro Circuit Breaker: Approaching volatility window (&lt;30m).</span>
        </div>
      )}

      {isOngoing && (
        <div className="mt-2.5 flex items-center gap-1.5 text-[11px] text-red-300 bg-red-500/10 border border-red-500/20 px-2.5 py-1.5 rounded-lg">
          <ShieldAlert size={12} className="shrink-0 animate-bounce" />
          <span>News Active: Extreme tick volatility possible. Spread filter armed.</span>
        </div>
      )}
    </div>
  );
}
