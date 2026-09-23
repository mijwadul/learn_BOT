"use client";

import { useState, useEffect } from "react";
import { Database, HardDrive, CalendarDays, RefreshCw, AlertTriangle, ShieldCheck } from "lucide-react";

export default function DatabasePage() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [isBackfilling, setIsBackfilling] = useState(false);
  const [prevRowCount, setPrevRowCount] = useState<number | null>(null);

  const fetchHealth = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/database/health");
      const data = await res.json();
      if (data.status === "success") {
        setHealth(data);
      }
    } catch (err) {
      console.error("Failed to fetch DB health", err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  // FIX #9: Monitor backfill progress — reset tombol hanya setelah row_count berubah
  useEffect(() => {
    if (!isBackfilling || prevRowCount === null) return;
    if (health !== null && health.row_count !== undefined && health.row_count > prevRowCount) {
      setIsBackfilling(false);
      setActionMessage(`Backfill selesai! Total rows sekarang: ${health.row_count.toLocaleString()}`);
      setPrevRowCount(null);
    }
  }, [health, isBackfilling, prevRowCount]);

  const handleForceBackfill = async () => {
    if (!confirm("Are you sure you want to run Force Backfill? This will fetch historical data from MT5 in the background.")) return;

    setIsBackfilling(true);
    setActionMessage(null);
    // Simpan row count sebelum backfill
    setPrevRowCount(health?.row_count ?? null);
    try {
      const res = await fetch("http://localhost:8000/api/data/sync", { method: "POST" });
      const data = await res.json();
      setActionMessage(data.message + " — Monitoring progress via health check...");
    } catch (err) {
      setActionMessage("Error: Failed to trigger backfill.");
      setIsBackfilling(false);
    }
    // FIX #9: Jangan reset isBackfilling dengan setTimeout — polling health hingga row_count berubah
  };

  return (
    <div className="p-6 h-full flex flex-col overflow-y-auto">
      <div className="mb-8 shrink-0 flex flex-col md:flex-row md:justify-between md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-black text-white tracking-widest flex items-center gap-3">
            <Database className="text-brand-blue" /> DATABASE MANAGEMENT
          </h1>
          <p className="text-white/50 mt-2">Monitor data ingestion health and synchronize with MT5 history.</p>
        </div>
      </div>

      {actionMessage && (
        <div className="mb-6 p-4 rounded-xl bg-brand-green/20 border border-brand-green/50 text-brand-green font-medium shrink-0 flex items-center gap-2">
          <ShieldCheck size={20} />
          {actionMessage}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* DB Health Status */}
        <div className="glass-panel p-6 flex flex-col gap-6">
          <div className="flex items-center gap-3 mb-2">
            <HardDrive className="text-white/70" size={24} />
            <h2 className="text-xl font-bold text-white">Storage Health</h2>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-black/40 border border-white/5 rounded-xl p-4 flex flex-col items-center justify-center">
              <span className="text-xs text-white/50 uppercase tracking-widest mb-2">Total Rows</span>
              <span className="text-3xl font-black text-white">
                {loading ? "..." : health?.row_count !== undefined ? health.row_count.toLocaleString() : "0"}
              </span>
            </div>
            
            <div className="bg-black/40 border border-white/5 rounded-xl p-4 flex flex-col items-center justify-center text-center">
               <span className="text-xs text-white/50 uppercase tracking-widest mb-2">Status</span>
               <span className="text-lg font-bold text-brand-green flex items-center gap-2">
                 <ShieldCheck size={20} /> Healthy
               </span>
            </div>
          </div>

          <div className="mt-2 p-4 bg-white/5 border border-white/10 rounded-xl">
             <div className="flex items-center gap-3 mb-4 text-white/80 font-semibold">
               <CalendarDays size={20} /> Date Range (Historical Data)
             </div>
             <div className="flex justify-between items-center text-sm mb-2">
               <span className="text-white/50">Earliest Record:</span>
               <span className="text-white font-mono">{health?.min_date ? new Date(health.min_date).toLocaleString() : "N/A"}</span>
             </div>
             <div className="flex justify-between items-center text-sm">
               <span className="text-white/50">Latest Record:</span>
               <span className="text-white font-mono">{health?.max_date ? new Date(health.max_date).toLocaleString() : "N/A"}</span>
             </div>
          </div>
        </div>

        {/* Sync Controls */}
        <div className="glass-panel p-6 flex flex-col">
          <div className="flex items-center gap-3 mb-4">
            <RefreshCw className="text-brand-blue" size={24} />
            <h2 className="text-xl font-bold text-white">Data Synchronization</h2>
          </div>
          
          <p className="text-sm text-white/60 mb-6">
            Ingestion agent continuously updates the database in real-time. If there is a missing gap in historical data (e.g. after weekend offline), you can trigger a forced backfill from MetaTrader 5.
          </p>
          
          <div className="bg-brand-blue/10 border border-brand-blue/30 rounded-xl p-4 mb-6">
            <h3 className="text-brand-blue font-bold text-sm mb-2 flex items-center gap-2">
              <AlertTriangle size={16} /> Data Warning
            </h3>
            <p className="text-xs text-white/60">
              Running Force Backfill requires intensive CPU and MT5 connection. It will fetch thousands of M1 candles and re-calculate BBMA Multi-Timeframe features. Check Terminal Logs to monitor progress.
            </p>
          </div>

          <div className="mt-auto">
            <button 
              onClick={handleForceBackfill}
              disabled={isBackfilling}
              className={`w-full py-4 rounded-xl font-bold text-lg flex items-center justify-center gap-3 transition-colors ${
                isBackfilling 
                  ? "bg-white/10 text-white/50 cursor-not-allowed" 
                  : "bg-brand-blue/20 text-brand-blue border border-brand-blue/50 hover:bg-brand-blue/40"
              }`}
            >
              <RefreshCw className={isBackfilling ? "animate-spin" : ""} size={24} />
              {isBackfilling ? "TRIGGERING BACKFILL..." : "FORCE BACKFILL MT5"}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
