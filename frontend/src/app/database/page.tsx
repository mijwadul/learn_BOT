"use client";

import { useState, useEffect } from "react";
import { 
  Database, 
  HardDrive, 
  CalendarDays, 
  RefreshCw, 
  AlertTriangle, 
  ShieldCheck, 
  Zap, 
  Activity, 
  CheckCircle2, 
  Clock 
} from "lucide-react";
import { getApiBaseUrl } from "@/config";

export default function DatabasePage() {
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState<{ text: string; type: "success" | "info" | "error" } | null>(null);
  const [isSyncingLatest, setIsSyncingLatest] = useState(false);
  const [isBackfilling, setIsBackfilling] = useState(false);
  const [prevRowCount, setPrevRowCount] = useState<number | null>(null);

  const fetchHealth = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/database/health`);
      const data = await res.json();
      if (data.status === "success") {
        setHealth(data);

        // Pantau status sinkronisasi dari backend
        if (data.sync_status) {
          const s = data.sync_status;
          if (s.is_syncing) {
            if (s.sync_type === "incremental") {
              setIsSyncingLatest(true);
            } else if (s.sync_type === "backfill") {
              setIsBackfilling(true);
            }
            if (s.message) {
              setActionMessage({ text: s.message, type: "info" });
            }
          } else {
            // Jika proses baru selesai
            if (isSyncingLatest || isBackfilling) {
              setIsSyncingLatest(false);
              setIsBackfilling(false);
              if (s.error) {
                setActionMessage({ text: s.error, type: "error" });
              } else if (s.message && s.message !== "Idle") {
                setActionMessage({ text: s.message, type: "success" });
              }
            }
          }
        }
      }
    } catch (err) {
      console.error("Failed to fetch DB health", err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchHealth();
    // Jika sedang sync, poll lebih cepat (2 detik), jika idle poll per 10 detik
    const pollInterval = (isSyncingLatest || isBackfilling) ? 2000 : 10000;
    const interval = setInterval(fetchHealth, pollInterval);
    return () => clearInterval(interval);
  }, [isSyncingLatest, isBackfilling]);

  // Handle Sync Data Terbaru (Inkremental)
  const handleSyncLatest = async () => {
    setIsSyncingLatest(true);
    setActionMessage({ text: "Memulai sinkronisasi candle terbaru dari MT5...", type: "info" });
    setPrevRowCount(health?.row_count ?? null);

    try {
      const res = await fetch(`${getApiBaseUrl()}/api/data/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force_rebuild: false })
      });
      const data = await res.json();
      if (data.status === "success") {
        setActionMessage({ text: data.message, type: "info" });
      } else if (data.status === "busy") {
        setActionMessage({ text: data.message, type: "info" });
      } else {
        setActionMessage({ text: data.message || "Gagal sinkronisasi data.", type: "error" });
        setIsSyncingLatest(false);
      }
    } catch (err) {
      setActionMessage({ text: "Error: Gagal memicu sinkronisasi data.", type: "error" });
      setIsSyncingLatest(false);
    }
  };

  // Handle Full Rebuild Force Backfill
  const handleForceBackfill = async () => {
    if (!confirm("PERINGATAN: Force Backfill akan me-rebuild ulang 5.000.000 candle historis dari MT5 dari nol. Apakah Anda yakin ingin melanjutkan?")) return;

    setIsBackfilling(true);
    setActionMessage({ text: "Memulai Force Backfill (Rebuild 5jt candle)...", type: "info" });
    setPrevRowCount(health?.row_count ?? null);

    try {
      const res = await fetch(`${getApiBaseUrl()}/api/data/backfill`, { method: "POST" });
      const data = await res.json();
      if (data.status === "success") {
        setActionMessage({ text: data.message, type: "info" });
      } else {
        setActionMessage({ text: data.message || "Gagal memicu backfill.", type: "error" });
        setIsBackfilling(false);
      }
    } catch (err) {
      setActionMessage({ text: "Error: Gagal memicu backfill.", type: "error" });
      setIsBackfilling(false);
    }
  };

  const isBusy = isSyncingLatest || isBackfilling;

  return (
    <div className="p-3 sm:p-4 md:p-6 min-h-full flex flex-col">
      <div className="mb-6 md:mb-8 shrink-0 flex flex-col md:flex-row md:justify-between md:items-center gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-widest flex items-center gap-2 sm:gap-3">
            <Database className="text-brand-blue" /> DATABASE MANAGEMENT
          </h1>
          <p className="text-white/50 text-xs sm:text-sm mt-1">Monitor data ingestion health and synchronize with MT5 history.</p>
        </div>

        {/* Live MT5 Connection Badge */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-black/40 border border-white/10 text-xs self-start md:self-auto">
          <div className={`w-2.5 h-2.5 rounded-full ${health?.mt5_connected ? "bg-brand-green animate-pulse" : "bg-red-500"}`} />
          <span className="text-white/70 font-medium">MT5:</span>
          <span className={health?.mt5_connected ? "text-brand-green font-bold" : "text-red-400 font-bold"}>
            {health?.mt5_connected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      {actionMessage && (
        <div className={`mb-4 sm:mb-6 p-3 sm:p-4 rounded-xl text-xs sm:text-sm font-medium shrink-0 flex items-center gap-2.5 transition-all ${
          actionMessage.type === "success" 
            ? "bg-brand-green/20 border border-brand-green/50 text-brand-green"
            : actionMessage.type === "error"
            ? "bg-red-500/20 border border-red-500/50 text-red-400"
            : "bg-brand-blue/20 border border-brand-blue/50 text-brand-blue"
        }`}>
          {actionMessage.type === "success" ? (
            <CheckCircle2 size={18} className="shrink-0" />
          ) : actionMessage.type === "error" ? (
            <AlertTriangle size={18} className="shrink-0" />
          ) : (
            <RefreshCw size={18} className="shrink-0 animate-spin" />
          )}
          <span>{actionMessage.text}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        
        {/* DB Health Status */}
        <div className="glass-panel p-4 sm:p-6 flex flex-col gap-4 sm:gap-6">
          <div className="flex items-center justify-between mb-1 sm:mb-2">
            <div className="flex items-center gap-2 sm:gap-3">
              <HardDrive className="text-white/70" size={20} />
              <h2 className="text-lg sm:text-xl font-bold text-white">Storage Health</h2>
            </div>
            {isBusy && (
              <span className="text-[11px] font-semibold text-brand-blue flex items-center gap-1.5 bg-brand-blue/10 px-2.5 py-1 rounded-full border border-brand-blue/30">
                <RefreshCw size={12} className="animate-spin" /> Syncing...
              </span>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <div className="bg-black/40 border border-white/5 rounded-xl p-3 sm:p-4 flex flex-col items-center justify-center">
              <span className="text-[10px] sm:text-xs text-white/50 uppercase tracking-widest mb-1 sm:mb-2">Total Rows</span>
              <span className="text-xl sm:text-3xl font-black text-white">
                {loading ? "..." : health?.row_count !== undefined ? health.row_count.toLocaleString() : "0"}
              </span>
            </div>
            
            <div className="bg-black/40 border border-white/5 rounded-xl p-3 sm:p-4 flex flex-col items-center justify-center text-center">
               <span className="text-[10px] sm:text-xs text-white/50 uppercase tracking-widest mb-1 sm:mb-2">Status</span>
               <span className="text-sm sm:text-lg font-bold text-brand-green flex items-center gap-1.5 sm:gap-2">
                 <ShieldCheck size={18} /> Healthy
               </span>
            </div>
          </div>

          {/* Date Comparison: DB vs MT5 */}
          <div className="mt-1 sm:mt-2 p-3 sm:p-4 bg-white/5 border border-white/10 rounded-xl space-y-2.5">
             <div className="flex items-center gap-2 text-white/80 font-semibold text-xs sm:text-sm">
               <CalendarDays size={18} /> Historical Range & Sync Gap
             </div>

             <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center text-xs py-1 border-b border-white/5 gap-1">
               <span className="text-white/50">Earliest Record (DB):</span>
               <span className="text-white font-mono text-[11px] sm:text-xs">
                 {health?.min_date ? new Date(health.min_date).toLocaleString() : "N/A"}
               </span>
             </div>

             <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center text-xs py-1 border-b border-white/5 gap-1">
               <span className="text-white/50">Latest Record (DB):</span>
               <span className="text-white font-mono text-[11px] sm:text-xs font-semibold">
                 {health?.max_date ? new Date(health.max_date).toLocaleString() : "N/A"}
               </span>
             </div>

             <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center text-xs pt-1 gap-1">
               <span className="text-white/50 flex items-center gap-1">
                 <Clock size={13} className="text-brand-blue" /> Latest Candle (MT5):
               </span>
               <span className="text-brand-blue font-mono text-[11px] sm:text-xs font-bold">
                 {health?.mt5_latest_time ? new Date(health.mt5_latest_time).toLocaleString() : health?.mt5_connected ? "Checking..." : "MT5 Offline"}
               </span>
             </div>
          </div>
        </div>

        {/* Sync Controls */}
        <div className="glass-panel p-4 sm:p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <RefreshCw className="text-brand-blue" size={24} />
              <h2 className="text-lg sm:text-xl font-bold text-white">Data Synchronization</h2>
            </div>
            
            <p className="text-xs sm:text-sm text-white/60 mb-5 leading-relaxed">
              Ingestion agent menjaga data tetap sinkron. Anda dapat menjalankan sinkronisasi cepat untuk memeriksa candle terbaru di MT5 dan menyambungkannya ke database tanpa menghapus data yang ada.
            </p>

            {/* Tombol Utama: SYNC DATA TERBARU */}
            <div className="p-4 rounded-xl bg-gradient-to-br from-brand-blue/15 to-transparent border border-brand-blue/30 mb-5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-brand-blue flex items-center gap-1.5">
                  <Zap size={14} /> Quick Incremental Sync
                </span>
                <span className="text-[10px] text-white/40">Safe &bull; No Data Loss</span>
              </div>
              <p className="text-xs text-white/60 mb-4">
                Mengecek candle baru dari MT5 sejak record terakhir ({health?.max_date ? new Date(health.max_date).toLocaleTimeString() : "DB"}) dan langsung menyambungkannya (append) ke database.
              </p>
              
              <button 
                onClick={handleSyncLatest}
                disabled={isBusy}
                className={`w-full py-3.5 px-4 rounded-xl font-bold text-sm sm:text-base flex items-center justify-center gap-2.5 transition-all shadow-lg ${
                  isSyncingLatest 
                    ? "bg-brand-blue/30 text-brand-blue border border-brand-blue/50 cursor-not-allowed" 
                    : isBusy
                    ? "bg-white/5 text-white/30 cursor-not-allowed border border-white/5"
                    : "bg-brand-blue hover:bg-brand-blue/80 text-white shadow-brand-blue/20 hover:shadow-brand-blue/40 cursor-pointer"
                }`}
              >
                <RefreshCw className={isSyncingLatest ? "animate-spin" : ""} size={18} />
                {isSyncingLatest ? "MENYINKRONKAN DENGAN MT5..." : "SYNC DATA TERBARU (MT5)"}
              </button>
            </div>
          </div>

          {/* Opsi Sekunder: Force Backfill Rebuild */}
          <div className="pt-4 border-t border-white/10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold text-white/40 flex items-center gap-1">
                <AlertTriangle size={12} className="text-yellow-500/70" /> Full Historical Rebuild
              </span>
              <span className="text-[10px] text-yellow-500/60 font-mono">5,000,000 Candles</span>
            </div>
            
            <button 
              onClick={handleForceBackfill}
              disabled={isBusy}
              className={`w-full py-2.5 px-3 rounded-lg font-medium text-xs flex items-center justify-center gap-2 transition-colors ${
                isBackfilling 
                  ? "bg-white/10 text-white/50 cursor-not-allowed" 
                  : isBusy
                  ? "bg-white/5 text-white/20 cursor-not-allowed"
                  : "bg-white/5 hover:bg-red-500/10 text-white/60 hover:text-red-300 border border-white/10 hover:border-red-500/30 cursor-pointer"
              }`}
            >
              <RefreshCw className={isBackfilling ? "animate-spin" : ""} size={14} />
              {isBackfilling ? "TRIGGERING FULL BACKFILL..." : "FORCE BACKFILL MT5 (REBUILD)"}
            </button>
          </div>

        </div>

      </div>
    </div>
  );
}

