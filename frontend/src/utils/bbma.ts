/**
 * BBMA (Bollinger Bands + Moving Average) Quantitative Indicator Calculations
 * for Lightweight-Charts.
 */

export interface CandleBar {
  time: any;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface LineData {
  time: any;
  value: number;
}

/**
 * Simple Moving Average (SMA)
 */
export function calculateSMA(bars: CandleBar[], period: number, field: keyof CandleBar = "close"): LineData[] {
  const result: LineData[] = [];
  if (!bars || bars.length < period) return result;

  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += Number(bars[i][field]);
  }
  result.push({ time: bars[period - 1].time, value: sum / period });

  for (let i = period; i < bars.length; i++) {
    sum += Number(bars[i][field]) - Number(bars[i - period][field]);
    result.push({ time: bars[i].time, value: sum / period });
  }

  return result;
}

/**
 * Bollinger Bands (Period 20, StdDev 2)
 */
export function calculateBollingerBands(
  bars: CandleBar[],
  period: number = 20,
  multiplier: number = 2
): { top: LineData[]; mid: LineData[]; low: LineData[] } {
  const top: LineData[] = [];
  const mid: LineData[] = [];
  const low: LineData[] = [];

  if (!bars || bars.length < period) return { top, mid, low };

  for (let i = period - 1; i < bars.length; i++) {
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += bars[i - j].close;
    }
    const mean = sum / period;

    let varianceSum = 0;
    for (let j = 0; j < period; j++) {
      varianceSum += Math.pow(bars[i - j].close - mean, 2);
    }
    const stdDev = Math.sqrt(varianceSum / period);

    const time = bars[i].time;
    mid.push({ time, value: Number(mean.toFixed(2)) });
    top.push({ time, value: Number((mean + multiplier * stdDev).toFixed(2)) });
    low.push({ time, value: Number((mean - multiplier * stdDev).toFixed(2)) });
  }

  return { top, mid, low };
}

/**
 * Exponential Moving Average (EMA)
 */
export function calculateEMA(bars: CandleBar[], period: number = 50, field: keyof CandleBar = "close"): LineData[] {
  const result: LineData[] = [];
  if (!bars || bars.length < period) return result;

  const k = 2 / (period + 1);

  // Initial SMA as starting point
  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += Number(bars[i][field]);
  }
  let currentEMA = sum / period;
  result.push({ time: bars[period - 1].time, value: Number(currentEMA.toFixed(2)) });

  for (let i = period; i < bars.length; i++) {
    const val = Number(bars[i][field]);
    currentEMA = val * k + currentEMA * (1 - k);
    result.push({ time: bars[i].time, value: Number(currentEMA.toFixed(2)) });
  }

  return result;
}

/**
 * Linear Weighted Moving Average (LWMA)
 * Weight: sum(i * P_i) / (n * (n + 1) / 2)
 */
export function calculateLWMA(
  bars: CandleBar[],
  period: number,
  field: "high" | "low" | "close" = "close"
): LineData[] {
  const result: LineData[] = [];
  if (!bars || bars.length < period) return result;

  const weightSum = (period * (period + 1)) / 2;

  for (let i = period - 1; i < bars.length; i++) {
    let weightedSum = 0;
    for (let j = 0; j < period; j++) {
      const weight = period - j;
      const barVal = Number(bars[i - j][field]);
      weightedSum += barVal * weight;
    }
    const lwma = weightedSum / weightSum;
    result.push({ time: bars[i].time, value: Number(lwma.toFixed(2)) });
  }

  return result;
}
