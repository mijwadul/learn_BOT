"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, LineStyle, IPriceLine } from "lightweight-charts";
import { Clock, Eye, EyeOff, Layers, Crosshair } from "lucide-react";
import { getWsBaseUrl, getApiBaseUrl } from "@/config";
import {
  CandleBar,
  calculateBollingerBands,
  calculateEMA,
  calculateLWMA,
} from "@/utils/bbma";

const TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];

export interface PositionItem {
  symbol: string;
  ticket: number;
  type: "BUY" | "SELL";
  volume: number;
  open_price: number;
  current_price: number;
  sl?: number;
  tp?: number;
  profit?: number;
}

interface TradingChartProps {
  isLive: boolean;
  symbol?: string;
  positions?: PositionItem[];
}

export default function TradingChart({
  isLive,
  symbol = "XAUUSD",
  positions: propPositions,
}: TradingChartProps) {
  const [timeframe, setTimeframe] = useState("M1");
  const [showBBMA, setShowBBMA] = useState(true);
  const [showEMA50, setShowEMA50] = useState(true);
  const [showOrders, setShowOrders] = useState(true);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // Indicator line series refs
  const topBBRef = useRef<ISeriesApi<"Line"> | null>(null);
  const midBBRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lowBBRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const lwma5HighRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lwma10HighRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lwma5LowRef = useRef<ISeriesApi<"Line"> | null>(null);
  const lwma10LowRef = useRef<ISeriesApi<"Line"> | null>(null);

  // Active price lines for open positions
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const barsRef = useRef<CandleBar[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fallback local positions if not passed via props
  const [localPositions, setLocalPositions] = useState<PositionItem[]>([]);
  const activePositions = propPositions ?? localPositions;

  // Poll positions if not provided by prop
  useEffect(() => {
    if (propPositions) return;
    const fetchPositions = async () => {
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/state`);
        const data = await res.json();
        if (data.open_positions) {
          setLocalPositions(data.open_positions);
        }
      } catch (err) {
        // silent
      }
    };
    fetchPositions();
    const interval = setInterval(fetchPositions, 3000);
    return () => clearInterval(interval);
  }, [propPositions]);

  // Recalculate and update indicator series
  const updateIndicators = useCallback(() => {
    const bars = barsRef.current;
    if (!bars || bars.length === 0) return;

    if (showBBMA) {
      const bb = calculateBollingerBands(bars, 20, 2);
      topBBRef.current?.setData(bb.top);
      midBBRef.current?.setData(bb.mid);
      lowBBRef.current?.setData(bb.low);

      const l5h = calculateLWMA(bars, 5, "high");
      const l10h = calculateLWMA(bars, 10, "high");
      const l5l = calculateLWMA(bars, 5, "low");
      const l10l = calculateLWMA(bars, 10, "low");

      lwma5HighRef.current?.setData(l5h);
      lwma10HighRef.current?.setData(l10h);
      lwma5LowRef.current?.setData(l5l);
      lwma10LowRef.current?.setData(l10l);
    } else {
      topBBRef.current?.setData([]);
      midBBRef.current?.setData([]);
      lowBBRef.current?.setData([]);
      lwma5HighRef.current?.setData([]);
      lwma10HighRef.current?.setData([]);
      lwma5LowRef.current?.setData([]);
      lwma10LowRef.current?.setData([]);
    }

    if (showEMA50) {
      const ema = calculateEMA(bars, 50, "close");
      ema50Ref.current?.setData(ema);
    } else {
      ema50Ref.current?.setData([]);
    }
  }, [showBBMA, showEMA50]);

  // Draw or refresh price lines for active orders
  const refreshPriceLines = useCallback(() => {
    if (!seriesRef.current) return;

    // 1. Remove old price lines
    priceLinesRef.current.forEach((pl) => {
      try {
        seriesRef.current?.removePriceLine(pl);
      } catch (e) {
        // ignore
      }
    });
    priceLinesRef.current = [];

    if (!showOrders || !activePositions || activePositions.length === 0) return;

    // 2. Create lines for each position matching current symbol
    activePositions.forEach((pos) => {
      if (pos.symbol && pos.symbol !== symbol) return;

      const isBuy = pos.type === "BUY";
      // Entry Line
      const entryLine = seriesRef.current?.createPriceLine({
        price: pos.open_price,
        color: isBuy ? "#38bdf8" : "#fb923c",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `${pos.type} #${pos.ticket} (${pos.volume}L)`,
      });
      if (entryLine) priceLinesRef.current.push(entryLine);

      // Stop Loss Line
      if (pos.sl && pos.sl > 0) {
        const slLine = seriesRef.current?.createPriceLine({
          price: pos.sl,
          color: "#ef4444",
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: `SL #${pos.ticket}`,
        });
        if (slLine) priceLinesRef.current.push(slLine);
      }

      // Take Profit Line
      if (pos.tp && pos.tp > 0) {
        const tpLine = seriesRef.current?.createPriceLine({
          price: pos.tp,
          color: "#22c55e",
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: `TP #${pos.ticket}`,
        });
        if (tpLine) priceLinesRef.current.push(tpLine);
      }
    });
  }, [showOrders, activePositions, symbol]);

  // Initialize chart canvas once
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(255, 255, 255, 0.5)",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.04)" },
        horzLines: { color: "rgba(255, 255, 255, 0.04)" },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: { timeVisible: true, secondsVisible: false },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    // Technical indicator line series with BBMA institutional colors
    const topBB = chart.addLineSeries({
      color: "rgba(59, 130, 246, 0.7)",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      title: "Top BB",
    });
    const midBB = chart.addLineSeries({
      color: "rgba(234, 179, 8, 0.9)",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      title: "Mid BB",
    });
    const lowBB = chart.addLineSeries({
      color: "rgba(59, 130, 246, 0.7)",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      title: "Low BB",
    });

    const ema50 = chart.addLineSeries({
      color: "#f97316",
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      title: "EMA 50",
    });

    const lwma5High = chart.addLineSeries({
      color: "#f43f5e",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      title: "LWMA 5 High",
    });
    const lwma10High = chart.addLineSeries({
      color: "#be123c",
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: "LWMA 10 High",
    });

    const lwma5Low = chart.addLineSeries({
      color: "#10b981",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      title: "LWMA 5 Low",
    });
    const lwma10Low = chart.addLineSeries({
      color: "#047857",
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: "LWMA 10 Low",
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    topBBRef.current = topBB;
    midBBRef.current = midBB;
    lowBBRef.current = lowBB;
    ema50Ref.current = ema50;
    lwma5HighRef.current = lwma5High;
    lwma10HighRef.current = lwma10High;
    lwma5LowRef.current = lwma5Low;
    lwma10LowRef.current = lwma10Low;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight || 350,
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

  // Update price lines whenever active positions or toggle changes
  useEffect(() => {
    refreshPriceLines();
  }, [refreshPriceLines]);

  // Update indicators whenever toggle changes
  useEffect(() => {
    updateIndicators();
  }, [updateIndicators]);

  // Fetch initial candles per timeframe via HTTP to populate immediately
  const fetchTimeframeCandles = async (tf: string) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/market/candles?timeframe=${tf}&count=250`);
      const data = await res.json();
      if (data.status === "success" && data.candles && seriesRef.current) {
        const bars: CandleBar[] = data.candles.map((c: any) => ({
          time: c.time as any,
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
        }));
        barsRef.current = bars;
        seriesRef.current.setData(bars);
        updateIndicators();
        chartRef.current?.timeScale().fitContent();
      }
    } catch (err) {
      console.warn("Failed to fetch initial candles for tf", tf, err);
    }
  };

  // Switch timeframe & connect WebSocket
  useEffect(() => {
    fetchTimeframeCandles(timeframe);

    let retryDelay = 2000;
    const connect = () => {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      const ws = new WebSocket(`${getWsBaseUrl()}/ws/market_data?timeframe=${timeframe}`);
      wsRef.current = ws;
      ws.onopen = () => {
        retryDelay = 2000;
      };
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "history" && seriesRef.current) {
            const bars: CandleBar[] = (msg.data as any[]).map((c: any) => ({
              time: c.time as any,
              open: Number(c.open),
              high: Number(c.high),
              low: Number(c.low),
              close: Number(c.close),
            }));
            barsRef.current = bars;
            seriesRef.current.setData(bars);
            updateIndicators();
            chartRef.current?.timeScale().fitContent();
          } else if (msg.type === "candle" && seriesRef.current) {
            const newBar: CandleBar = {
              time: msg.data.time as any,
              open: Number(msg.data.open),
              high: Number(msg.data.high),
              low: Number(msg.data.low),
              close: Number(msg.data.close),
            };
            seriesRef.current.update(newBar);

            // Update local bars cache
            const lastIdx = barsRef.current.length - 1;
            if (lastIdx >= 0 && barsRef.current[lastIdx].time === newBar.time) {
              barsRef.current[lastIdx] = newBar;
            } else {
              barsRef.current.push(newBar);
            }
            updateIndicators();
          }
        } catch (err) {
          console.error("WS Parse Error", err);
        }
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
  }, [timeframe, updateIndicators]);

  return (
    <div className="w-full h-full flex flex-col relative select-none">
      {/* Timeframe & Overlays Toolbar */}
      <div className="flex flex-wrap items-center justify-between px-3 py-2 border-b border-white/5 bg-black/20 shrink-0 gap-2">
        {/* Timeframe Selector */}
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

        {/* Indicator Toggles & Meta Badges */}
        <div className="flex items-center gap-2 sm:gap-3 text-xs">
          {/* BBMA Overlays Toggle */}
          <button
            onClick={() => setShowBBMA(!showBBMA)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold transition-all border ${
              showBBMA
                ? "bg-blue-500/20 text-blue-400 border-blue-500/30"
                : "bg-white/5 text-white/40 border-white/5 hover:text-white/70"
            }`}
            title="Toggle Bollinger Bands (20) & LWMA (5/10)"
          >
            <Layers size={11} />
            <span>BBMA</span>
          </button>

          {/* EMA 50 Toggle */}
          <button
            onClick={() => setShowEMA50(!showEMA50)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold transition-all border ${
              showEMA50
                ? "bg-orange-500/20 text-orange-400 border-orange-500/30"
                : "bg-white/5 text-white/40 border-white/5 hover:text-white/70"
            }`}
            title="Toggle EMA 50 Major Trend line"
          >
            <span>EMA 50</span>
          </button>

          {/* Active Orders Toggle */}
          <button
            onClick={() => setShowOrders(!showOrders)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold transition-all border ${
              showOrders && activePositions.length > 0
                ? "bg-cyan-500/20 text-cyan-400 border-cyan-500/30 font-bold"
                : "bg-white/5 text-white/40 border-white/5 hover:text-white/70"
            }`}
            title="Toggle Active Orders (Entry / SL / TP)"
          >
            <Crosshair size={11} />
            <span>Orders ({activePositions.length})</span>
          </button>

          <span className="text-white/70 font-mono font-bold hidden sm:inline">{symbol}</span>
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
