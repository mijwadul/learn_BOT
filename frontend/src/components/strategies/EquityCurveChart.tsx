"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  CrosshairMode,
} from "lightweight-charts";
import { TrendingUp, AlertCircle } from "lucide-react";

export interface EquityPoint {
  time: number | string;
  value: number;
}

interface EquityCurveChartProps {
  data: EquityPoint[];
  passed?: boolean;
  symbol: string;
  mode: string;
}

export default function EquityCurveChart({
  data,
  passed = true,
  symbol,
  mode,
}: EquityCurveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || !data || data.length === 0) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255, 255, 255, 0.45)",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.04)" },
        horzLines: { color: "rgba(255, 255, 255, 0.04)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        scaleMargins: {
          top: 0.15,
          bottom: 0.15,
        },
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.1)",
        timeVisible: true,
        secondsVisible: false,
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 240,
    });

    // Area Series: Green if passed, Amber/Red if failed
    const lineColor = passed ? "#22c55e" : "#f43f5e";
    const topColor = passed ? "rgba(34, 197, 94, 0.35)" : "rgba(244, 63, 94, 0.35)";
    const bottomColor = passed ? "rgba(34, 197, 94, 0.0)" : "rgba(244, 63, 94, 0.0)";

    const areaSeries = chart.addAreaSeries({
      lineColor,
      topColor,
      bottomColor,
      lineWidth: 2,
      priceFormat: {
        type: "price",
        precision: 2,
        minMove: 0.01,
      },
    });

    // Normalize and sort points
    const formattedPoints = data
      .filter((p) => p && p.time && typeof p.value === "number" && !isNaN(p.value))
      .map((p) => {
        let tVal: any = p.time;
        if (typeof tVal === "string" && !tVal.includes("-")) {
          const num = Number(tVal);
          if (!isNaN(num)) tVal = num;
        }
        return {
          time: tVal,
          value: p.value,
        };
      })
      .sort((a, b) => {
        const ta = typeof a.time === "number" ? a.time : new Date(a.time).getTime() / 1000;
        const tb = typeof b.time === "number" ? b.time : new Date(b.time).getTime() / 1000;
        return ta - tb;
      });

    // Remove duplicates on time key (lightweight-charts requires strictly ascending time)
    const uniquePoints: any[] = [];
    const seenTimes = new Set();
    for (const pt of formattedPoints) {
      if (!seenTimes.has(pt.time)) {
        seenTimes.add(pt.time);
        uniquePoints.push(pt);
      }
    }

    if (uniquePoints.length > 0) {
      areaSeries.setData(uniquePoints);
      chart.timeScale().fitContent();
    }

    chartRef.current = chart;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 240,
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
  }, [data, passed, symbol, mode]);

  if (!data || data.length === 0) {
    return (
      <div className="w-full h-48 rounded-xl bg-black/30 border border-white/5 flex flex-col items-center justify-center text-center p-4">
        <TrendingUp className="w-8 h-8 text-white/20 mb-2" />
        <span className="text-xs font-semibold text-white/40">
          Belum ada data kurva ekuitas OOS untuk {symbol} ({mode.toUpperCase()})
        </span>
        <span className="text-[11px] text-white/30 mt-1">
          Klik tombol &quot;Evaluasi Ulang OOS&quot; untuk menjalankan simulasi VectorBT
        </span>
      </div>
    );
  }

  const initialVal = data[0]?.value ?? 100;
  const finalVal = data[data.length - 1]?.value ?? initialVal;
  const deltaPct = initialVal > 0 ? ((finalVal - initialVal) / initialVal) * 100 : 0;

  return (
    <div className="w-full flex flex-col">
      <div className="flex items-center justify-between mb-1 px-1">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold text-white/60 uppercase tracking-wider">
            Kurva Ekuitas OOS ({mode.toUpperCase()})
          </span>
          <span
            className={`text-[11px] font-black px-1.5 py-0.5 rounded ${
              deltaPct >= 0
                ? "bg-emerald-500/20 text-emerald-400"
                : "bg-rose-500/20 text-rose-400"
            }`}
          >
            {deltaPct >= 0 ? "+" : ""}
            {deltaPct.toFixed(2)}%
          </span>
        </div>
        <span className="text-[10px] text-white/40 font-mono">
          Start: ${initialVal.toLocaleString()} → Final: ${finalVal.toLocaleString()}
        </span>
      </div>
      <div
        ref={containerRef}
        className="w-full h-52 sm:h-60 rounded-xl bg-black/40 border border-white/10 overflow-hidden relative"
      />
    </div>
  );
}
