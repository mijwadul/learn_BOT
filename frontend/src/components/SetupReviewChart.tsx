"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  LineStyle,
  CrosshairMode,
} from "lightweight-charts";
import { Eye, EyeOff, Loader2 } from "lucide-react";

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  sma_20?: number | null;
  bb_upper?: number | null;
  bb_lower?: number | null;
  ema_50?: number | null;
  lwma_5_h?: number | null;
  lwma_10_h?: number | null;
  lwma_5_l?: number | null;
  lwma_10_l?: number | null;
}

interface SetupReviewChartProps {
  candles: Candle[];
  entryPrice: number;
  entryTime: number; // unix timestamp (seconds)
  sl: number;
  tp: number;
  action: "BUY" | "SELL";
  tfLabel: string; // "M1" | "M5" | "M15" | "M30" | "H1"
  currentTimeframe?: string;
  onTimeframeChange?: (tf: string) => void;
  isLoadingTf?: boolean;
}

export default function SetupReviewChart({
  candles,
  entryPrice,
  entryTime,
  sl,
  tp,
  action,
  tfLabel,
  currentTimeframe,
  onTimeframeChange,
  isLoadingTf = false,
}: SetupReviewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [showBbma, setShowBbma] = useState(true);

  const activeTf = (currentTimeframe || tfLabel || "M5").toUpperCase();
  const timeframes = ["M1", "M5", "M15", "M30", "H1"];

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

    // 1. Candlestick Series
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    const bars = candles.map((c) => ({
      time: c.time as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    candleSeries.setData(bars);

    // 2. Indikator BBMA Lengkap
    if (showBbma) {
      // Top BB & Low BB
      const bbUpperSeries = chart.addLineSeries({
        color: "#818cf8",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        title: "Top BB",
      });
      const bbLowerSeries = chart.addLineSeries({
        color: "#818cf8",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        title: "Low BB",
      });

      // Mid BB (SMA 20)
      const sma20Series = chart.addLineSeries({
        color: "#38bdf8",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        title: "Mid BB",
      });

      // EMA 50
      const ema50Series = chart.addLineSeries({
        color: "#06b6d4",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        title: "EMA 50",
      });

      // LWMA 5 High & LWMA 10 High
      const lwma5HSeries = chart.addLineSeries({
        color: "#f87171",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        title: "LWMA 5H",
      });
      const lwma10HSeries = chart.addLineSeries({
        color: "#ef4444",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        title: "LWMA 10H",
      });

      // LWMA 5 Low & LWMA 10 Low
      const lwma5LSeries = chart.addLineSeries({
        color: "#4ade80",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        title: "LWMA 5L",
      });
      const lwma10LSeries = chart.addLineSeries({
        color: "#22c55e",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        title: "LWMA 10L",
      });

      // Populate BBMA line data
      const upperData = candles.filter((c) => c.bb_upper != null).map((c) => ({ time: c.time as any, value: c.bb_upper! }));
      const lowerData = candles.filter((c) => c.bb_lower != null).map((c) => ({ time: c.time as any, value: c.bb_lower! }));
      const smaData = candles.filter((c) => c.sma_20 != null).map((c) => ({ time: c.time as any, value: c.sma_20! }));
      const emaData = candles.filter((c) => c.ema_50 != null).map((c) => ({ time: c.time as any, value: c.ema_50! }));
      const lwma5HData = candles.filter((c) => c.lwma_5_h != null).map((c) => ({ time: c.time as any, value: c.lwma_5_h! }));
      const lwma10HData = candles.filter((c) => c.lwma_10_h != null).map((c) => ({ time: c.time as any, value: c.lwma_10_h! }));
      const lwma5LData = candles.filter((c) => c.lwma_5_l != null).map((c) => ({ time: c.time as any, value: c.lwma_5_l! }));
      const lwma10LData = candles.filter((c) => c.lwma_10_l != null).map((c) => ({ time: c.time as any, value: c.lwma_10_l! }));

      if (upperData.length > 0) bbUpperSeries.setData(upperData);
      if (lowerData.length > 0) bbLowerSeries.setData(lowerData);
      if (smaData.length > 0) sma20Series.setData(smaData);
      if (emaData.length > 0) ema50Series.setData(emaData);
      if (lwma5HData.length > 0) lwma5HSeries.setData(lwma5HData);
      if (lwma10HData.length > 0) lwma10HSeries.setData(lwma10HData);
      if (lwma5LData.length > 0) lwma5LSeries.setData(lwma5LData);
      if (lwma10LData.length > 0) lwma10LSeries.setData(lwma10LData);
    }

    // Garis ENTRY — kuning dashed
    candleSeries.createPriceLine({
      price: entryPrice,
      color: "#facc15",
      lineWidth: 2,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "ENTRY @" + entryPrice.toFixed(2),
    });

    // Garis SL — merah solid
    candleSeries.createPriceLine({
      price: sl,
      color: "#ef4444",
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      axisLabelVisible: true,
      title: "SL @" + sl.toFixed(2),
    });

    // Garis TP — hijau solid
    candleSeries.createPriceLine({
      price: tp,
      color: "#22c55e",
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      axisLabelVisible: true,
      title: "TP @" + tp.toFixed(2),
    });

    // Marker arrow di candle entry terdekat
    // Cari candle yang paling mendekati entryTime
    let closestMarkerTime = entryTime;
    if (candles.length > 0) {
      let minDiff = Infinity;
      for (const c of candles) {
        const diff = Math.abs(c.time - entryTime);
        if (diff < minDiff) {
          minDiff = diff;
          closestMarkerTime = c.time;
        }
      }
    }

    candleSeries.setMarkers([
      {
        time: closestMarkerTime as any,
        position: action === "BUY" ? "belowBar" : "aboveBar",
        shape: action === "BUY" ? "arrowUp" : "arrowDown",
        color: "#facc15",
        text: `${action} @ ${entryPrice.toFixed(2)}`,
        size: 1.5,
      },
    ]);

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 340,
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
  }, [candles, entryPrice, entryTime, sl, tp, action, showBbma]);

  return (
    <div className="relative w-full h-full flex flex-col">
      {/* Top Chart Toolbar: Timeframe Selector + BBMA Toggle + Legend */}
      <div className="absolute top-2 left-2 right-2 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        {/* Left: Timeframe Switcher Buttons */}
        <div className="flex items-center gap-1 bg-black/80 backdrop-blur-md p-1 rounded-xl border border-white/10 pointer-events-auto shadow-lg">
          {timeframes.map((tf) => {
            const isSelected = activeTf === tf;
            return (
              <button
                key={tf}
                type="button"
                onClick={() => onTimeframeChange && onTimeframeChange(tf)}
                disabled={isLoadingTf}
                className={`px-2 py-0.5 rounded-lg text-[11px] font-bold transition-all flex items-center gap-1 ${
                  isSelected
                    ? "bg-brand-green text-black shadow-md shadow-brand-green/30"
                    : "text-white/60 hover:text-white hover:bg-white/10"
                } disabled:opacity-50 cursor-pointer`}
              >
                {isSelected && isLoadingTf && <Loader2 size={10} className="animate-spin" />}
                <span>{tf}</span>
              </button>
            );
          })}
        </div>

        {/* Right: Order Level Badges + Toggle BBMA */}
        <div className="flex items-center gap-2 pointer-events-auto">
          {/* Order Lines Badge */}
          <div className="hidden sm:flex items-center gap-2.5 bg-black/85 backdrop-blur-md px-2.5 py-1 rounded-xl border border-white/10 text-[10px] font-mono shadow-lg">
            <span className="flex items-center gap-1 text-yellow-300 font-semibold">
              <span className="w-2.5 h-0.5 bg-yellow-300 rounded" /> Entry
            </span>
            <span className="flex items-center gap-1 text-rose-400 font-semibold">
              <span className="w-2.5 h-0.5 bg-rose-400 rounded" /> SL
            </span>
            <span className="flex items-center gap-1 text-emerald-400 font-semibold">
              <span className="w-2.5 h-0.5 bg-emerald-400 rounded" /> TP
            </span>
          </div>

          {/* Toggle BBMA Visibility Button */}
          <button
            type="button"
            onClick={() => setShowBbma(!showBbma)}
            className={`px-2.5 py-1 rounded-xl text-[11px] font-bold flex items-center gap-1.5 transition-all shadow-lg border ${
              showBbma
                ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40 hover:bg-cyan-500/30"
                : "bg-white/5 text-white/40 border-white/10 hover:text-white hover:bg-white/10"
            } cursor-pointer`}
            title={showBbma ? "Sembunyikan Indikator BBMA" : "Tampilkan Indikator BBMA"}
          >
            {showBbma ? <Eye size={12} /> : <EyeOff size={12} />}
            <span>BBMA {showBbma ? "ON" : "OFF"}</span>
          </button>
        </div>
      </div>

      {/* Chart Canvas */}
      <div ref={containerRef} className="w-full h-full flex-1" />
    </div>
  );
}
