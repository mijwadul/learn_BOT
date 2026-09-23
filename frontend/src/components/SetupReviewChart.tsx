"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  LineStyle,
  CrosshairMode,
} from "lightweight-charts";

interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface SetupReviewChartProps {
  candles: Candle[];
  entryPrice: number;
  entryTime: number; // unix timestamp (seconds)
  sl: number;
  tp: number;
  action: "BUY" | "SELL";
  tfLabel: string; // "M5" atau "M15"
}

export default function SetupReviewChart({
  candles,
  entryPrice,
  entryTime,
  sl,
  tp,
  action,
  tfLabel,
}: SetupReviewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    // Destroy chart lama saat setup berganti
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255, 255, 255, 0.4)",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.04)" },
        horzLines: { color: "rgba(255, 255, 255, 0.04)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "rgba(255, 255, 255, 0.1)" },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    // Set data candle M5/M15
    const bars = candles.map((c) => ({
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeries.setData(bars);

    // Garis ENTRY — kuning dashed
    candleSeries.createPriceLine({
      price: entryPrice,
      color: "#facc15",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "ENTRY @" + entryPrice.toFixed(2),
    });

    // Garis SL — merah solid
    candleSeries.createPriceLine({
      price: sl,
      color: "#ef4444",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      axisLabelVisible: true,
      title: "SL @" + sl.toFixed(2),
    });

    // Garis TP — hijau solid
    candleSeries.createPriceLine({
      price: tp,
      color: "#22c55e",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      axisLabelVisible: true,
      title: "TP @" + tp.toFixed(2),
    });

    // Marker arrow di candle entry
    candleSeries.setMarkers([
      {
        time: entryTime as any,
        position: action === "BUY" ? "belowBar" : "aboveBar",
        shape: action === "BUY" ? "arrowUp" : "arrowDown",
        color: "#facc15",
        text: action,
        size: 1.5,
      },
    ]);

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 280,
        });
      }
    };
    const resizeObserver = new ResizeObserver(handleResize);
    if (containerRef.current) resizeObserver.observe(containerRef.current);
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  // Re-render saat setup berganti (entryTime berubah = setup baru)
  }, [candles, entryPrice, entryTime, sl, tp, action]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="relative w-full h-full">
      {/* Label timeframe di pojok kiri atas */}
      <span className="absolute top-2 left-2 z-10 text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/10 text-white/50 pointer-events-none">
        {tfLabel}
      </span>
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
}
