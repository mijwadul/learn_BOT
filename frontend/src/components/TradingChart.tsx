"use client";

import { useState, useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi } from "lightweight-charts";
import { Clock, Activity } from "lucide-react";
import { getWsBaseUrl, getApiBaseUrl } from "@/config";

const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

export default function TradingChart({ isLive }: { isLive: boolean }) {
  const [timeframe, setTimeframe] = useState("M1");
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Inisialisasi chart satu kali saat mount
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "rgba(255, 255, 255, 0.5)" },
      grid: { vertLines: { color: "rgba(255, 255, 255, 0.05)" }, horzLines: { color: "rgba(255, 255, 255, 0.05)" } },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: { timeVisible: true, secondsVisible: false },
    });
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444", borderVisible: false,
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    chartRef.current = chart;
    seriesRef.current = candleSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight || 300,
        });
      }
    };
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(chartContainerRef.current);
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      resizeObserver.disconnect();
      chart.remove();
    };
  }, []);

  // Fetch initial candles per timeframe via HTTP to populate immediately
  const fetchTimeframeCandles = async (tf: string) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/market/candles?timeframe=${tf}&count=200`);
      const data = await res.json();
      if (data.status === "success" && data.candles && seriesRef.current) {
        const bars = data.candles.map((c: any) => ({
          time: c.time as any, open: c.open, high: c.high, low: c.low, close: c.close,
        }));
        seriesRef.current.setData(bars);
        chartRef.current?.timeScale().fitContent();
      }
    } catch (err) {
      console.warn("Failed to fetch initial candles for tf", tf, err);
    }
  };

  // Switch timeframe & connect WebSocket for that timeframe
  useEffect(() => {
    // 1. Fetch initial candles immediately
    fetchTimeframeCandles(timeframe);

    // 2. Connect WebSocket with timeframe query param
    let retryDelay = 2000;
    const connect = () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      const ws = new WebSocket(`${getWsBaseUrl()}/ws/market_data?timeframe=${timeframe}`);
      wsRef.current = ws;
      ws.onopen = () => { retryDelay = 2000; };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "history" && seriesRef.current) {
            const bars = (msg.data as any[]).map((c: any) => ({
              time: c.time as any, open: c.open, high: c.high, low: c.low, close: c.close,
            }));
            seriesRef.current.setData(bars);
            chartRef.current?.timeScale().fitContent();
          } else if (msg.type === "candle" && seriesRef.current) {
            seriesRef.current.update({
              time: msg.data.time as any, open: msg.data.open,
              high: msg.data.high, low: msg.data.low, close: msg.data.close,
            });
          }
        } catch (err) { console.error("WS Parse Error", err); }
      };
      ws.onclose = () => {
        wsRef.current = null;
        retryDelay = Math.min(retryDelay * 1.5, 30000);
        reconnectTimeoutRef.current = setTimeout(connect, retryDelay);
      };
      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [timeframe]);

  return (
    <div className="w-full h-full flex flex-col relative select-none">
      {/* Timeframe Switcher Toolbar */}
      <div className="flex flex-wrap items-center justify-between px-3 py-2 border-b border-white/5 bg-black/20 shrink-0 gap-2">
        <div className="flex items-center gap-1 sm:gap-1.5">
          <span className="text-[11px] font-bold text-white/50 mr-1 sm:mr-2 flex items-center gap-1">
            <Clock size={13} className="text-brand-green" /> TF:
          </span>
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-2 sm:px-2.5 py-0.5 sm:py-1 text-xs font-mono font-bold rounded-md transition-all cursor-pointer ${
                timeframe === tf
                  ? "bg-brand-green text-black shadow-sm font-black"
                  : "text-white/50 hover:text-white hover:bg-white/10"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="text-white/70 font-mono font-bold">XAUUSDm</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold bg-white/5 text-white/40 border border-white/5">
            {timeframe}
          </span>
          <span className={`w-2 h-2 rounded-full ${isLive ? "bg-brand-green animate-pulse" : "bg-yellow-500"}`} title={isLive ? "Live Market Streaming" : "Paused"} />
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="flex-1 w-full relative min-h-[350px]">
        <div ref={chartContainerRef} className="absolute inset-0 w-full h-full" />
      </div>
    </div>
  );
}

