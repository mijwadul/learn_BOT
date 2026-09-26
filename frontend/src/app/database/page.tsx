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
  Clock,
  Plus,
  Layers,
  ChevronRight
} from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import { ConfirmModal } from "@/components/ui/ConfirmModal";

export default function DatabasePage() {
  const toast = useToast();
  const [pairs, setPairs] = useState<any[]>([{ symbol: "XAUUSD", row_count: 0 }]);
  const [selectedPair, setSelectedPair] = useState<string>("XAUUSD");
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState<{ text: string; type: "success" | "info" | "error" } | null>(null);
  const [isSyncingLatest, setIsSyncingLatest] = useState(false);
  const [isBackfilling, setIsBackfilling] = useState(false);
  const [isBackfillModalOpen, setIsBackfillModalOpen] = useState(false);
  const [isAddPairModalOpen, setIsAddPairModalOpen] = useState(false);
  const [newPairInput, setNewPairInput] = useState("");
  const [isAddingPair, setIsAddingPair] = useState(false);

  // Fetch list of registered pairs
  const fetchPairs = async () => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/pairs`);
      const data = await res.json();
      if (data.status === "success" && data.pairs) {
        setPairs(data.pairs);
      }
    } catch (err) {
      console.error("Failed to fetch pairs", err);
    }
  };

  const fetchHealth = async (sym = selectedPair) => {
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/database/health?symbol=${sym}`);
      const data = await res.json();
      if (data.status === "success") {
        setHealth(data);

        // Pantau status sinkronisasi dari backend
        if (data.is_syncing !== undefined) {
          if (data.is_syncing) {
            setIsSyncingLatest(true);
          } else if (isSyncingLatest || isBackfilling) {
            setIsSyncingLatest(false);
            setIsBackfilling(false);
            fetchPairs(); // Refresh row counts
          }
        }
      }
    } catch (err) {
      console.error("Failed to fetch DB health", err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchPairs();
  }, []);

  useEffect(() => {
    fetchHealth(selectedPair);
    const pollInterval = (isSyncingLatest || isBackfilling) ? 2000 : 10000;
    const interval = setInterval(() => fetchHealth(selectedPair), pollInterval);
    return () => clearInterval(interval);
  }, [selectedPair, isSyncingLatest, isBackfilling]);

  // Handle Tambah Pair Baru
  const handleAddPair = async (e: React.FormEvent) => {
    e.preventDefault();
    const clean = newPairInput.trim().toUpperCase();
    if (!clean) return;

    setIsAddingPair(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/pairs/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: clean })
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.success(data.message, "Pair Terdaftar");
        await fetchPairs();
        setSelectedPair(clean);
        setIsAddPairModalOpen(false);
        setNewPairInput("");
      } else {
        toast.error(data.message || "Gagal mendaftarkan pair baru.", "Error");
      }
    } catch {
      toast.error("Gagal terhubung ke backend server.", "Error");
    } finally {
      setIsAddingPair(false);
    }
  };

  // Handle Sync Data Terbaru (Inkremental)
  const handleSyncLatest = async () => {
    setIsSyncingLatest(true);
    setActionMessage({ text: `Memulai sinkronisasi candle terbaru ${selectedPair} dari MT5...`, type: "info" });

    try {
      const res = await fetch(`${getApiBaseUrl()}/api/data/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: selectedPair, force_rebuild: false })
      });
      const data = await res.json();
      if (data.status === "success") {
        setActionMessage({ text: data.message, type: "info" });
        toast.info(data.message, `Sync ${selectedPair}`);
      } else if (data.status === "busy") {
        setActionMessage({ text: data.message, type: "info" });
      } else {
        setActionMessage({ text: data.message || "Gagal sinkronisasi data.", type: "error" });
        setIsSyncingLatest(false);
      }
    } catch {
      setActionMessage({ text: "Error: Gagal memicu sinkronisasi data.", type: "error" });
      setIsSyncingLatest(false);
    }
  };

  // Handle Full Rebuild Force Backfill
  const handleForceBackfill = async () => {
    setIsBackfillModalOpen(false);
    setIsBackfilling(true);
    setActionMessage({ text: `Memulai Force Backfill (Rebuild 5jt candle) untuk tabel ${health?.table_name || selectedPair}...`, type: "info" });
    toast.info(`Memulai Force Backfill ${selectedPair}...`, "Backfill");

    try {
      const res = await fetch(`${getApiBaseUrl()}/api/data/backfill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: selectedPair, total_candles: 5000000, force_rebuild: true })
      });
      const data = await res.json();
      if (data.status === "success") {
        setActionMessage({ text: data.message, type: "info" });
        toast.success(data.message, `Backfill ${selectedPair}`);
      } else {
        setActionMessage({ text: data.message || "Gagal memicu backfill.", type: "error" });
        toast.error(data.message || "Gagal memicu backfill.", "Gagal");
        setIsBackfilling(false);
      }
    } catch {
      setActionMessage({ text: "Error: Gagal memicu backfill.", type: "error" });
      toast.error("Gagal terhubung ke backend server.", "Error");
      setIsBackfilling(false);
    }
  };

  const isBusy = isSyncingLatest || isBackfilling;

  return (
    <div className="p-3 sm:p-4 md:p-6 min-h-full flex flex-col">
      {/* Page Header */}
      <div className="mb-4 sm:mb-6 shrink-0 flex flex-col md:flex-row md:justify-between md:items-center gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-widest flex items-center gap-2 sm:gap-3">
            <Database className="text-brand-blue" /> DATABASE MANAGEMENT
          </h1>
          <p className="text-white/50 text-xs sm:text-sm mt-1">Multi-Pair Ingestion & Database Health (Isolated Tables per Pair).</p>
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

      {/* Multi-Pair Selection Tab Bar */}
      <div className="mb-5 p-3 rounded-xl bg-black/40 border border-white/10 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 overflow-x-auto py-1">
          <span className="text-xs font-semibold text-white/50 uppercase tracking-wider mr-1 flex items-center gap-1">
            <Layers size={14} className="text-brand-blue" /> Target Pair:
          </span>
          {(pairs.length > 0 ? pairs.map(p => p.symbol) : ["XAUUSD"]).map((sym) => {
            const isSelected = selectedPair === sym;
            const pairData = pairs.find(p => p.symbol === sym);
            return (
              <button
                key={sym}
                onClick={() => setSelectedPair(sym)}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                  isSelected
                    ? "bg-brand-blue text-white shadow-lg shadow-brand-blue/30 border border-brand-blue/60"
                    : "bg-white/5 hover:bg-white/10 text-white/70 border border-white/5"
                }`}
              >
                <span>{sym}</span>
                {pairData && (
                  <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${isSelected ? "bg-black/30 text-white" : "bg-white/10 text-white/50"}`}>
                    {pairData.row_count > 0 ? `${(pairData.row_count / 1000).toFixed(0)}k` : "0"}
                  </span>
                )}
              </button>
            );
          })}
          {/* Tombol Tambah Pair Baru */}
          <button
            onClick={() => setIsAddPairModalOpen(true)}
            className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-brand-blue/20 text-white/80 hover:text-white border border-dashed border-white/20 hover:border-brand-blue/40 text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ml-1"
          >
            <Plus size={14} className="text-brand-blue" /> Tambah Pair
          </button>
        </div>
      </div>

      {/* Info Deteksi Simbol Broker & Tabel */}
      <div className="mb-4 sm:mb-6 px-4 py-2.5 rounded-xl bg-brand-blue/10 border border-brand-blue/20 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-white/60">Pair Terpilih:</span>
          <span className="font-bold text-white font-mono text-sm">{selectedPair}</span>
          <ChevronRight size={14} className="text-white/30" />
          <span className="text-white/60">Simbol Broker MT5:</span>
          <span className="font-bold text-brand-green font-mono text-sm">{health?.broker_symbol || "Resolving..."}</span>
        </div>
        <div className="flex items-center gap-2 text-white/50">
          <span>Tabel Database Terisolasi:</span>
          <span className="font-mono text-white/80 font-semibold bg-black/40 px-2 py-0.5 rounded border border-white/5">
            {health?.table_name || `market_data_${selectedPair.toLowerCase()}`}
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
              <h2 className="text-lg sm:text-xl font-bold text-white">Storage Health ({selectedPair})</h2>
            </div>
            {isBusy && (
              <span className="text-[11px] font-semibold text-brand-blue flex items-center gap-1.5 bg-brand-blue/10 px-2.5 py-1 rounded-full border border-brand-blue/30">
                <RefreshCw size={12} className="animate-spin" /> Syncing...
              </span>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <div className="bg-black/40 border border-white/5 rounded-xl p-3 sm:p-4 flex flex-col items-center justify-center">
              <span className="text-[10px] sm:text-xs text-white/50 uppercase tracking-widest mb-1 sm:mb-2">Total Rows ({selectedPair})</span>
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
               <CalendarDays size={18} /> Historical Range ({selectedPair})
             </div>

             <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center text-xs py-1 border-b border-white/5 gap-1">
               <span className="text-white/50">Earliest Record (DB):</span>
               <span className="text-white font-mono text-[11px] sm:text-xs">
                 {health?.min_date ? new Date(health.min_date).toLocaleString() : "Belum ada data"}
               </span>
             </div>

             <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center text-xs py-1 border-b border-white/5 gap-1">
               <span className="text-white/50">Latest Record (DB):</span>
               <span className="text-white font-mono text-[11px] sm:text-xs font-semibold">
                 {health?.max_date ? new Date(health.max_date).toLocaleString() : "Belum ada data"}
               </span>
             </div>

             <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center text-xs pt-1 gap-1">
               <span className="text-white/50 flex items-center gap-1">
                 <Clock size={13} className="text-brand-blue" /> Latest MT5 Candle ({health?.broker_symbol || selectedPair}):
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
              <h2 className="text-lg sm:text-xl font-bold text-white">Synchronization ({selectedPair})</h2>
            </div>
            
            <p className="text-xs sm:text-sm text-white/60 mb-5 leading-relaxed">
              Tarik data histori dan candle terkini khusus pair <strong className="text-white">{selectedPair}</strong> ({health?.broker_symbol || selectedPair}). Data disimpan ke tabel terisolasi tanpa mempengaruhi pair lainnya.
            </p>

            {/* Tombol Utama: SYNC DATA TERBARU */}
            <div className="p-4 rounded-xl bg-gradient-to-br from-brand-blue/15 to-transparent border border-brand-blue/30 mb-5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-brand-blue flex items-center gap-1.5">
                  <Zap size={14} /> Quick Incremental Sync ({selectedPair})
                </span>
                <span className="text-[10px] text-white/40">Tabel: {health?.table_name}</span>
              </div>
              <p className="text-xs text-white/60 mb-4">
                Mengecek candle baru dari MT5 untuk {health?.broker_symbol || selectedPair} sejak record terakhir ({health?.max_date ? new Date(health.max_date).toLocaleTimeString([], { hour12: false }) : "DB"}) dan menyambungkannya ke database.
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
                {isSyncingLatest ? `MENYINKRONKAN ${selectedPair}...` : `SYNC DATA TERBARU (${selectedPair})`}
              </button>
            </div>
          </div>

          {/* Opsi Sekunder: Force Backfill Rebuild */}
          <div className="pt-4 border-t border-white/10">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold text-white/40 flex items-center gap-1">
                <AlertTriangle size={12} className="text-yellow-500/70" /> Rebuild Khusus {selectedPair} (Aman untuk Pair Lain)
              </span>
              <span className="text-[10px] text-yellow-500/60 font-mono">5,000,000 Candles</span>
            </div>
            
            <button 
              onClick={() => setIsBackfillModalOpen(true)}
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
              {isBackfilling ? `REBUILDING ${selectedPair}...` : `FORCE BACKFILL ${selectedPair} (REBUILD)`}
            </button>
          </div>

        </div>

      </div>

      {/* Modal Tambah Pair */}
      {isAddPairModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-panel max-w-md w-full p-6 border border-white/20 rounded-2xl shadow-2xl">
            <h3 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
              <Plus className="text-brand-blue" size={20} /> Tambah Pair Baru
            </h3>
            <p className="text-xs text-white/60 mb-4">
              Ketik nama pair standar (contoh: <strong className="text-white">EURUSD</strong>, <strong className="text-white">GBPUSD</strong>, <strong className="text-white">BTCUSD</strong>). Sistem akan otomatis mendeteksi simbol broker MT5 Anda terlepas dari akhiran (m, c, .pro, dsb) dan membuatkan subfolder otak & tabel database tersendiri.
            </p>
            <form onSubmit={handleAddPair}>
              <div className="mb-4">
                <label className="text-[11px] font-semibold text-white/60 uppercase tracking-wider block mb-1">
                  Nama Pair Standar:
                </label>
                <input
                  type="text"
                  placeholder="Misal: EURUSD"
                  value={newPairInput}
                  onChange={(e) => setNewPairInput(e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-black/60 border border-white/15 text-white font-mono font-bold focus:border-brand-blue outline-none text-sm"
                  autoFocus
                />
              </div>
              <div className="flex justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsAddPairModalOpen(false)}
                  className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-white/70 text-xs font-semibold transition-colors"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={isAddingPair || !newPairInput.trim()}
                  className="px-5 py-2 rounded-xl bg-brand-blue hover:bg-brand-blue/80 text-white text-xs font-bold transition-all disabled:opacity-50"
                >
                  {isAddingPair ? "Mendaftarkan..." : "Daftarkan Pair"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal Konfirmasi Backfill */}
      <ConfirmModal
        isOpen={isBackfillModalOpen}
        onClose={() => setIsBackfillModalOpen(false)}
        onConfirm={handleForceBackfill}
        title={`Konfirmasi Force Backfill ${selectedPair}`}
        description={`PERINGATAN: Force Backfill akan membersihkan dan men-download ulang 5.000.000 candle historis untuk tabel ${health?.table_name || selectedPair} secara penuh. Data pair lain TIDAK AKAN terganggu. Lanjutkan?`}
        confirmText="Mulai Rebuild"
        cancelText="Batal"
        variant="warning"
        isLoading={isBackfilling}
      />
    </div>
  );
}
