"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi } from "lightweight-charts";
import { getWsBaseUrl } from "@/config";

export default function TradingChart({ isLive }: { isLive: boolean }) {
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

  // FIX #4: WebSocket SELALU connect saat mount (tidak bergantung pada isLive)
  // Backend mengirim 200 historical candles saat connect pertama (type:"history")
  // FIX #10: Auto-reconnect dengan exponential backoff jika koneksi terputus
  useEffect(() => {
    let retryDelay = 2000;
    const connect = () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;
      const ws = new WebSocket(`${getWsBaseUrl()}/ws/market_data`);
      wsRef.current = ws;
      ws.onopen = () => { retryDelay = 2000; };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "history" && seriesRef.current) {
            // Render semua candle historis sekaligus untuk mengisi chart
            const bars = (msg.data as any[]).map((c: any) => ({
              time: c.time as any, open: c.open, high: c.high, low: c.low, close: c.close,
            }));
            seriesRef.current.setData(bars);
            chartRef.current?.timeScale().fitContent();
          } else if (msg.type === "candle" && seriesRef.current) {
            // Update candle terkini secara real-time
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
  }, []);

  return (
    <div className="w-full h-full min-h-[300px] md:min-h-[400px] relative">
      {!isLive && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40 backdrop-blur-sm rounded-lg">
          <p className="text-white/50 font-medium">System Offline - Waiting for Tick Data</p>
        </div>
      )}
      <div ref={chartContainerRef} className="w-full h-full" />
    </div>
  );
}
