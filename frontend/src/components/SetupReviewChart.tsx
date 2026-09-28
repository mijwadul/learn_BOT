"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  ISeriesApi,
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
  entryTime: number;
  sl: number;
  tp: number;
  action: "BUY" | "SELL";
  tfLabel: string;
  currentTimeframe?: string;
  onTimeframeChange?: (tf: string) => void;
  isLoadingTf?: boolean;
}

interface SeriesRefs {
  candle:  ISeriesApi<"Candlestick"> | null;
  bbUpper: ISeriesApi<"Line"> | null;
  bbLower: ISeriesApi<"Line"> | null;
  sma20:   ISeriesApi<"Line"> | null;
  ema50:   ISeriesApi<"Line"> | null;
  lwma5H:  ISeriesApi<"Line"> | null;
  lwma10H: ISeriesApi<"Line"> | null;
  lwma5L:  ISeriesApi<"Line"> | null;
  lwma10L: ISeriesApi<"Line"> | null;
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
  const containerRef   = useRef<HTMLDivElement>(null);
  const chartRef       = useRef<IChartApi | null>(null);
  const seriesRef      = useRef<SeriesRefs>({
    candle: null, bbUpper: null, bbLower: null, sma20: null,
    ema50: null, lwma5H: null, lwma10H: null, lwma5L: null, lwma10L: null,
  });
  const priceLineRef   = useRef<{ entry: any; sl: any; tp: any }>({ entry: null, sl: null, tp: null });
  const [showBbma, setShowBbma] = useState(true);

  const activeTf   = (currentTimeframe || tfLabel || "M5").toUpperCase();
  const timeframes = ["M1", "M5", "M15", "M30", "H1"];

  // ── Effect 1: Init chart SEKALI saat mount — TIDAK bergantung pada data ───
  useEffect(() => {
    if (!containerRef.current) return;

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
      width:  containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 340,
    });

    // Buat semua series sekali — tidak akan di-destroy sampai komponen unmount
    const s = seriesRef.current;
    s.candle  = chart.addCandlestickSeries({
      upColor: "#22c55e", downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e", wickDownColor: "#ef4444",
    });
    s.bbUpper  = chart.addLineSeries({ color: "#818cf8", lineWidth: 1, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    s.bbLower  = chart.addLineSeries({ color: "#818cf8", lineWidth: 1, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    s.sma20    = chart.addLineSeries({ color: "#38bdf8", lineWidth: 2, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    s.ema50    = chart.addLineSeries({ color: "#06b6d4", lineWidth: 2, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    s.lwma5H   = chart.addLineSeries({ color: "#f87171", lineWidth: 1, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    s.lwma10H  = chart.addLineSeries({ color: "#ef4444", lineWidth: 2, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    s.lwma5L   = chart.addLineSeries({ color: "#4ade80", lineWidth: 1, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
    s.lwma10L  = chart.addLineSeries({ color: "#22c55e", lineWidth: 2, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });

    chartRef.current = chart;

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width:  containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 340,
        });
      }
    };
    const ro = new ResizeObserver(handleResize);
    ro.observe(containerRef.current);
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = {
        candle: null, bbUpper: null, bbLower: null, sma20: null,
        ema50: null, lwma5H: null, lwma10H: null, lwma5L: null, lwma10L: null,
      };
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Effect 2: Update DATA — tidak recreate chart, hanya setData() ─────────
  useEffect(() => {
    const s = seriesRef.current;
    if (!s.candle || candles.length === 0) return;

    s.candle.setData(
      candles.map((c) => ({ time: c.time as any, open: c.open, high: c.high, low: c.low, close: c.close }))
    );

    // Update entry marker
    let closestTime = entryTime;
    let minDiff = Infinity;
    for (const c of candles) {
      const diff = Math.abs(c.time - entryTime);
      if (diff < minDiff) { minDiff = diff; closestTime = c.time; }
    }
    s.candle.setMarkers([{
      time: closestTime as any,
      position: action === "BUY" ? "belowBar" : "aboveBar",
      shape:    action === "BUY" ? "arrowUp"   : "arrowDown",
      color: "#facc15",
      text: `${action} @ ${entryPrice.toFixed(2)}`,
      size: 1.5,
    }]);

    // Update BBMA series — set data kosong jika showBbma = false
    const toLine = (key: keyof Candle) =>
      showBbma
        ? candles.filter((c) => c[key] != null).map((c) => ({ time: c.time as any, value: c[key] as number }))
        : [];

    s.bbUpper?.setData(toLine("bb_upper"));
    s.bbLower?.setData(toLine("bb_lower"));
    s.sma20?.setData(toLine("sma_20"));
    s.ema50?.setData(toLine("ema_50"));
    s.lwma5H?.setData(toLine("lwma_5_h"));
    s.lwma10H?.setData(toLine("lwma_10_h"));
    s.lwma5L?.setData(toLine("lwma_5_l"));
    s.lwma10L?.setData(toLine("lwma_10_l"));

    chartRef.current?.timeScale().fitContent();
  }, [candles, action, entryPrice, entryTime, showBbma]);

  // ── Effect 3: Update Price Lines (Entry / SL / TP) ────────────────────────
  useEffect(() => {
    const s = seriesRef.current;
    if (!s.candle) return;

    // Hapus price lines lama sebelum tambah yang baru
    try { if (priceLineRef.current.entry) s.candle.removePriceLine(priceLineRef.current.entry); } catch (_) {}
    try { if (priceLineRef.current.sl)    s.candle.removePriceLine(priceLineRef.current.sl); }    catch (_) {}
    try { if (priceLineRef.current.tp)    s.candle.removePriceLine(priceLineRef.current.tp); }    catch (_) {}

    priceLineRef.current.entry = s.candle.createPriceLine({ price: entryPrice, color: "#facc15", lineWidth: 2, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "ENTRY @" + entryPrice.toFixed(2) });
    priceLineRef.current.sl    = s.candle.createPriceLine({ price: sl,         color: "#ef4444", lineWidth: 2, lineStyle: LineStyle.Solid,  axisLabelVisible: true, title: "SL @" + sl.toFixed(2) });
    priceLineRef.current.tp    = s.candle.createPriceLine({ price: tp,         color: "#22c55e", lineWidth: 2, lineStyle: LineStyle.Solid,  axisLabelVisible: true, title: "TP @" + tp.toFixed(2) });
  }, [entryPrice, sl, tp]);

  return (
    <div className="relative w-full h-full flex flex-col">
      <div className="absolute top-2 left-2 right-2 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        {/* Timeframe Switcher */}
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

        {/* Order Lines Badge + Toggle BBMA */}
        <div className="flex items-center gap-2 pointer-events-auto">
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

