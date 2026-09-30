"use client";

import { useState, useEffect, useCallback } from "react";
import { BarChart2, Brain, RefreshCw, Cpu, ChevronDown } from "lucide-react";
import { getApiBaseUrl } from "@/config";

interface FeatureEntry {
  feature: string;
  importance: number;
  rank: number;
}

interface FeatureImportanceCardProps {
  selectedPair?: string;
}

const MODE_OPTIONS = ["normal", "runner"] as const;
const IMP_TYPE_OPTIONS = ["gain", "split"] as const;
type Mode = (typeof MODE_OPTIONS)[number];
type ImpType = (typeof IMP_TYPE_OPTIONS)[number];

/** Warna gradient bar berdasarkan peringkat (1 = paling penting) */
function getBarColor(rank: number): string {
  const colors = [
    "from-emerald-400 to-green-500",
    "from-green-400 to-teal-500",
    "from-teal-400 to-cyan-500",
    "from-cyan-400 to-sky-500",
    "from-sky-400 to-blue-500",
    "from-blue-400 to-indigo-500",
    "from-indigo-400 to-violet-500",
    "from-violet-400 to-purple-500",
    "from-purple-400 to-fuchsia-500",
    "from-fuchsia-400 to-pink-500",
  ];
  return colors[(rank - 1) % colors.length];
}

export function FeatureImportanceCard({ selectedPair = "XAUUSD" }: FeatureImportanceCardProps) {
  const [mode, setMode] = useState<Mode>("normal");
  const [impType, setImpType] = useState<ImpType>("gain");
  const [features, setFeatures] = useState<FeatureEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const fetchFeatures = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `${getApiBaseUrl()}/api/strategies/features?symbol=${selectedPair}&mode=${mode}&top_n=10&importance_type=${impType}`;
      const res = await fetch(url);
      const data = await res.json();
      if (data.status === "success") {
        setFeatures(data.features || []);
        setLastUpdated(new Date().toLocaleTimeString("id-ID"));
      } else {
        setError(data.message || "Model belum dilatih.");
        setFeatures([]);
      }
    } catch {
      setError("Gagal terhubung ke backend.");
      setFeatures([]);
    } finally {
      setLoading(false);
    }
  }, [selectedPair, mode, impType]);

  useEffect(() => {
    fetchFeatures();
  }, [fetchFeatures]);

  const maxImp = features.length > 0 ? features[0].importance : 1;

  return (
    <div className="mb-4 rounded-2xl bg-black/40 border border-white/10 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/8">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-brand-green/15 flex items-center justify-center">
            <BarChart2 className="w-4 h-4 text-brand-green" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
              Top 10 Feature Importance
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md bg-brand-green/15 text-brand-green border border-brand-green/30 uppercase tracking-wider">
                Dapur AI
              </span>
            </h3>
            <p className="text-[11px] text-white/40 mt-0.5">
              Fitur teknikal yang paling dipercaya model ({selectedPair})
            </p>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {/* Mode toggle */}
          <div className="flex rounded-xl overflow-hidden border border-white/10 text-xs">
            {MODE_OPTIONS.map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-1.5 font-semibold transition-all cursor-pointer ${
                  mode === m
                    ? "bg-brand-green text-black"
                    : "bg-white/5 text-white/50 hover:bg-white/10"
                }`}
              >
                {m === "normal" ? "Scalp" : "Runner"}
              </button>
            ))}
          </div>

          {/* Importance type selector */}
          <div className="relative">
            <select
              value={impType}
              onChange={(e) => setImpType(e.target.value as ImpType)}
              className="appearance-none bg-white/5 border border-white/10 rounded-xl text-xs text-white/70 px-3 py-1.5 pr-7 cursor-pointer hover:bg-white/10 transition-all focus:outline-none focus:border-brand-green/50"
            >
              {IMP_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t} className="bg-zinc-900">
                  {t === "gain" ? "Gain" : "Split"}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-white/40 pointer-events-none" />
          </div>

          {/* Refresh button */}
          <button
            onClick={fetchFeatures}
            disabled={loading}
            className="w-7 h-7 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center hover:bg-white/10 transition-all cursor-pointer disabled:opacity-50"
            title="Refresh feature importance"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-white/60 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="p-5">
        {loading && features.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 gap-3">
            <div className="w-10 h-10 rounded-full border-2 border-brand-green/30 border-t-brand-green animate-spin" />
            <p className="text-xs text-white/40">Memuat feature importance...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-10 gap-3 text-center">
            <div className="w-10 h-10 rounded-full bg-amber-500/10 flex items-center justify-center">
              <Brain className="w-5 h-5 text-amber-400" />
            </div>
            <p className="text-xs text-amber-400/80 max-w-xs">{error}</p>
            <p className="text-[10px] text-white/30">
              Latih model terlebih dahulu untuk melihat fitur yang dipelajari AI.
            </p>
          </div>
        ) : features.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 gap-2 text-center">
            <Cpu className="w-8 h-8 text-white/20" />
            <p className="text-xs text-white/40">Tidak ada data feature importance.</p>
          </div>
        ) : (
          <>
            {/* Bar chart rows */}
            <div className="space-y-2.5">
              {features.map((f, idx) => {
                const pct = maxImp > 0 ? (f.importance / maxImp) * 100 : 0;
                const barColor = getBarColor(f.rank);
                return (
                  <div key={f.feature} className="group">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2 min-w-0">
                        <span
                          className="text-[10px] font-bold w-5 h-5 rounded-md flex items-center justify-center shrink-0"
                          style={{
                            background:
                              idx === 0
                                ? "rgba(52, 211, 153, 0.2)"
                                : "rgba(255,255,255,0.05)",
                            color: idx === 0 ? "#34d399" : "rgba(255,255,255,0.35)",
                          }}
                        >
                          {f.rank}
                        </span>
                        <span
                          className="text-xs font-mono truncate text-white/70 group-hover:text-white/90 transition-colors"
                          title={f.feature}
                        >
                          {f.feature}
                        </span>
                      </div>
                      <span className="text-xs font-bold text-white/50 ml-2 shrink-0 tabular-nums">
                        {f.importance.toFixed(2)}%
                      </span>
                    </div>
                    {/* Bar */}
                    <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                      <div
                        className={`h-full rounded-full bg-gradient-to-r ${barColor} transition-all duration-500`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Footer */}
            <div className="mt-4 pt-3 border-t border-white/5 flex items-center justify-between">
              <p className="text-[10px] text-white/30">
                Tipe:{" "}
                <span className="text-white/50 font-semibold uppercase">{impType}</span>
                {" · "}Mode:{" "}
                <span className="text-brand-green font-semibold uppercase">{mode}</span>
              </p>
              {lastUpdated && (
                <p className="text-[10px] text-white/30">Diperbarui {lastUpdated}</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
