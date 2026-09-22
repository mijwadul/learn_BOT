"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi } from "lightweight-charts";

export default function TradingChart({ isLive }: { isLive: boolean }) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255, 255, 255, 0.5)",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.05)" },
        horzLines: { color: "rgba(255, 255, 255, 0.05)" },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      }
    });

    const lineSeries = chart.addLineSeries({
      color: "#22c55e",
      lineWidth: 2,
    });

    chartRef.current = chart;
    seriesRef.current = lineSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, []);

  // Handle WebSocket Data
  useEffect(() => {
    if (!isLive || !seriesRef.current) return;

    const ws = new WebSocket("ws://localhost:8000/ws/market_data");

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "tick") {
          const timestamp = Math.floor(new Date(msg.data.timestamp).getTime() / 1000);
          seriesRef.current?.update({
            time: timestamp as any,
            value: msg.data.price
          });
        }
      } catch (err) {
        console.error("WS Parse Error", err);
      }
    };

    return () => {
      ws.close();
    };
  }, [isLive]);

  return (
    <div className="w-full h-full min-h-[400px] relative">
      {!isLive && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40 backdrop-blur-sm rounded-lg">
          <p className="text-white/50 font-medium">System Offline - Waiting for Tick Data</p>
        </div>
      )}
      <div ref={chartContainerRef} className="w-full h-full" />
    </div>
  );
}
