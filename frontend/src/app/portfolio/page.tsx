"use client";
import { useState, useEffect } from "react";
import { 
  Wallet, 
  RotateCcw, 
  Trash2, 
  AlertTriangle, 
  X, 
  Check, 
  ShieldCheck, 
  Layers, 
  FileText, 
  Brain, 
  History, 
  ChevronDown,
  ArrowUpRight,
  ArrowDownRight
} from "lucide-react";
import { getApiBaseUrl } from "@/config";

interface FreshStartOption {
  id: string;
  label: string;
  tableName: string;
  description: string;
  badge: string;
}

const FRESH_START_ITEMS: FreshStartOption[] = [
  {
    id: "trade_logs",
    label: "Riwayat Transaksi & Catatan PnL",
    tableName: "trade_logs",
    description: "Catatan tiket order BUY/SELL/CLOSE dari MT5 beserta nilai nominal profit/loss riil.",
    badge: "Core PnL"
  },
  {
    id: "decision_samples",
    label: "Sampel Keputusan Live AI",
    tableName: "live_decision_samples",
    description: "Feature vector numerik teknikal, probabilitas ML, dan outcome PnL saat eksekusi live.",
    badge: "AI Features"
  },
  {
    id: "journal",
    label: "Black Box Trade Journal",
    tableName: "trade_journal",
    description: "Log kronologis peristiwa trading AI, alasan XAI fitur dominan, dan snapshot chart M1.",
    badge: "Journal"
  },
  {
    id: "rlhf_setups",
    label: "Feedback & Label Trader (RLHF)",
    tableName: "approved / rejected / ignored",
    description: "Antrean setup sinyal dan riwayat evaluasi/persetujuan manual oleh trader.",
    badge: "RLHF"
  },
  {
    id: "hard_negatives",
    label: "Hard Negative Error Samples",
    tableName: "hard_negatives",
    description: "Sampel sinyal salah arah yang dicatat untuk koreksi OOS model AI.",
    badge: "OOS Eval"
  }
];

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState({ value: 0, equity: 0, open_positions: [] as any[] });
  const [isResetting, setIsResetting] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [selectedItems, setSelectedItems] = useState<string[]>(FRESH_START_ITEMS.map(i => i.id));
  const [preset, setPreset] = useState<string>("all");

  useEffect(() => {
    const fetchPortfolio = () => {
      fetch(`${getApiBaseUrl()}/api/state`)
        .then(res => res.json())
        .then(data => {
          if (data.portfolio) {
            setPortfolio({
              ...data.portfolio,
              open_positions: data.open_positions || []
            });
          }
        })
        .catch(err => console.error("Backend offline", err));
    };
    fetchPortfolio();
    const interval = setInterval(fetchPortfolio, 3000);
    return () => clearInterval(interval);
  }, []);

  // Handle Preset Change via Combo Box
  const handlePresetChange = (value: string) => {
    setPreset(value);
    if (value === "all") {
      setSelectedItems(FRESH_START_ITEMS.map(i => i.id));
    } else if (value === "trades_only") {
      setSelectedItems(["trade_logs", "journal"]);
    } else if (value === "ai_only") {
      setSelectedItems(["decision_samples", "rlhf_setups", "hard_negatives"]);
    }
  };

  // Toggle individual item
  const toggleItem = (id: string) => {
    let next: string[];
    if (selectedItems.includes(id)) {
      next = selectedItems.filter(item => item !== id);
    } else {
      next = [...selectedItems, id];
    }
    setSelectedItems(next);
    
    // Auto-detect preset state
    if (next.length === FRESH_START_ITEMS.length) {
      setPreset("all");
    } else if (next.length === 2 && next.includes("trade_logs") && next.includes("journal")) {
      setPreset("trades_only");
    } else if (next.length === 3 && next.includes("decision_samples") && next.includes("rlhf_setups") && next.includes("hard_negatives")) {
      setPreset("ai_only");
    } else {
      setPreset("custom");
    }
  };

  const handleConfirmReset = async () => {
    if (selectedItems.length === 0) {
      alert("Pilih minimal satu komponen data untuk di-drop.");
      return;
    }

    setIsResetting(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/trades/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targets: selectedItems })
      });
      const data = await res.json();
      if (data.status === "success") {
        setShowModal(false);
        alert("✅ Berhasil! Komponen data yang dipilih telah di-drop. Sistem siap untuk Fresh Start di akun cent baru.");
        window.location.reload();
      } else {
        alert("❌ Gagal mereset: " + (data.message || "Unknown error"));
      }
    } catch (err) {
      alert("❌ Error: Gagal terhubung ke server backend.");
    } finally {
      setIsResetting(false);
    }
  };

  const formatCurrency = (val: number) => {
    return (val || 0).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const profit = portfolio.equity - portfolio.value;
  const isProfit = profit >= 0;

  return (
    <div className="p-3 sm:p-4 md:p-6 min-h-full flex flex-col">
      <div className="mb-6 md:mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-widest flex items-center gap-2 sm:gap-3">
            <Wallet className="text-brand-green" /> PORTFOLIO
          </h1>
          <p className="text-white/50 text-xs sm:text-sm mt-1">Live overview of your assets and open positions</p>
        </div>

        <button
          onClick={() => setShowModal(true)}
          disabled={isResetting}
          className="self-start sm:self-auto py-2.5 px-4 rounded-xl text-xs font-bold tracking-wider uppercase flex items-center gap-2 transition-all bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 hover:border-red-500/50 shadow-lg shadow-red-500/10 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          title="Buka dialog checklist drop riwayat AI"
        >
          <RotateCcw className={isResetting ? "animate-spin" : ""} size={14} />
          {isResetting ? "RESETTING..." : "FRESH START: DROP RIWAYAT AI"}
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4 md:gap-6 mb-6 md:mb-8">
        <div className="glass-panel p-4 sm:p-6">
          <p className="text-white/50 text-xs sm:text-sm font-semibold uppercase tracking-wider mb-1 sm:mb-2">Total Balance</p>
          <p className="text-2xl sm:text-3xl lg:text-4xl font-black text-white" suppressHydrationWarning>
            ${formatCurrency(portfolio.value)}
          </p>
        </div>
        <div className="glass-panel p-4 sm:p-6">
          <p className="text-white/50 text-xs sm:text-sm font-semibold uppercase tracking-wider mb-1 sm:mb-2">Floating Profit/Loss</p>
          <p
            className={`text-2xl sm:text-3xl lg:text-4xl font-black flex items-center gap-1.5 sm:gap-2 ${isProfit ? 'text-brand-green' : 'text-brand-red'}`}
            suppressHydrationWarning
          >
            {isProfit ? '+' : ''}${formatCurrency(profit)}
            {isProfit ? <ArrowUpRight className="w-5 h-5 sm:w-7 sm:h-7" /> : <ArrowDownRight className="w-5 h-5 sm:w-7 sm:h-7" />}
          </p>
        </div>
        <div className="glass-panel p-4 sm:p-6 sm:col-span-2 md:col-span-1">
          <p className="text-white/50 text-xs sm:text-sm font-semibold uppercase tracking-wider mb-1 sm:mb-2">Equity</p>
          <p className="text-2xl sm:text-3xl lg:text-4xl font-black text-white" suppressHydrationWarning>
            ${formatCurrency(portfolio.equity)}
          </p>
        </div>
      </div>

      <h2 className="text-base sm:text-lg font-bold text-white mb-3 sm:mb-4">Open Positions ({portfolio.open_positions.length})</h2>

      {/* Mobile Card View for Open Positions */}
      <div className="md:hidden flex flex-col gap-3">
        {portfolio.open_positions.length === 0 ? (
          <div className="glass-panel p-6 text-center text-white/30 text-xs">
            Tidak ada posisi yang terbuka saat ini.
          </div>
        ) : (
          portfolio.open_positions.map((pos) => (
            <div key={pos.ticket} className="glass-panel p-4 flex flex-col gap-2 border-l-4 border-l-brand-blue">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="font-black text-white text-base">{pos.symbol}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-black ${pos.type === 'BUY' ? 'bg-brand-green/20 text-brand-green border border-brand-green/30' : 'bg-brand-red/20 text-brand-red border border-brand-red/30'}`}>
                    {pos.type}
                  </span>
                  <span className="text-white/40 text-xs font-mono">Vol: {pos.volume.toFixed(2)}</span>
                </div>
                <span className={`font-black text-sm font-mono ${pos.profit >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                  {pos.profit >= 0 ? '+' : ''}${pos.profit.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between items-center text-xs text-white/50 pt-2 border-t border-white/5 font-mono">
                <span>#{pos.ticket}</span>
                <span>Open: {pos.open_price.toFixed(3)}</span>
                <span>Now: {pos.current_price.toFixed(3)}</span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Desktop Table View for Open Positions */}
      <div className="hidden md:flex glass-panel flex-1 overflow-hidden flex-col">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-white/10 text-white/50 text-xs uppercase tracking-wider">
                <th className="p-4 font-medium">Ticket</th>
                <th className="p-4 font-medium">Symbol</th>
                <th className="p-4 font-medium">Type</th>
                <th className="p-4 font-medium">Volume</th>
                <th className="p-4 font-medium">Open Price</th>
                <th className="p-4 font-medium">Current Price</th>
                <th className="p-4 font-medium text-right">Profit</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {portfolio.open_positions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-4 text-center text-white/30">
                    Tidak ada posisi yang terbuka saat ini.
                  </td>
                </tr>
              ) : (
                portfolio.open_positions.map((pos) => (
                  <tr key={pos.ticket} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                    <td className="p-4 text-white/50">#{pos.ticket}</td>
                    <td className="p-4 font-bold text-white">{pos.symbol}</td>
                    <td className={`p-4 font-bold ${pos.type === 'BUY' ? 'text-brand-green' : 'text-brand-red'}`}>{pos.type}</td>
                    <td className="p-4 text-white/70">{pos.volume.toFixed(2)}</td>
                    <td className="p-4 text-white/70">{pos.open_price.toFixed(3)}</td>
                    <td className="p-4 text-white/70">{pos.current_price.toFixed(3)}</td>
                    <td className={`p-4 text-right font-bold ${pos.profit >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                      {pos.profit >= 0 ? '+' : ''}${pos.profit.toFixed(2)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Custom Fresh Start Modal Dialog with Custom Preset Combo Box & Checklist */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-150">
          <div className="relative w-full max-w-xl bg-[#0d111a] border border-red-500/30 rounded-2xl shadow-2xl shadow-red-950/60 flex flex-col max-h-[92vh] overflow-hidden">
            
            {/* Modal Header */}
            <div className="p-4 sm:p-5 border-b border-white/10 flex items-start justify-between bg-gradient-to-r from-red-500/15 via-transparent to-transparent">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-red-500/20 border border-red-500/40 flex items-center justify-center text-red-400 shrink-0">
                  <AlertTriangle size={20} />
                </div>
                <div>
                  <h3 className="text-base sm:text-lg font-bold text-white flex items-center gap-2">
                    Fresh Start: Drop Data Trading AI
                  </h3>
                  <p className="text-xs text-white/50 mt-0.5">
                    Pilih komponen data yang ingin di-drop untuk persiapan akun baru.
                  </p>
                </div>
              </div>
              <button
                onClick={() => !isResetting && setShowModal(false)}
                className="text-white/40 hover:text-white p-1.5 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-4 sm:p-5 overflow-y-auto flex flex-col gap-4 flex-1">
              
              {/* Custom Preset Selector / Combo Box */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-white/70 mb-1.5">
                  Pilihan Cepat (Preset Combo):
                </label>
                <div className="relative">
                  <select
                    value={preset}
                    onChange={(e) => handlePresetChange(e.target.value)}
                    className="w-full py-2.5 px-3.5 pr-10 rounded-xl bg-white/5 border border-white/15 text-white text-xs sm:text-sm font-medium focus:outline-none focus:border-red-500/50 focus:bg-white/10 transition-all appearance-none cursor-pointer"
                  >
                    <option value="all" className="bg-[#0d111a] text-white">
                      Semua Komponen (Full Fresh Start - 5 dari 5)
                    </option>
                    <option value="trades_only" className="bg-[#0d111a] text-white">
                      Hanya Riwayat Transaksi & PnL (Simpan Fitur AI)
                    </option>
                    <option value="ai_only" className="bg-[#0d111a] text-white">
                      Hanya Data Pembelajaran AI (Simpan Catatan Transaksi)
                    </option>
                    <option value="custom" className="bg-[#0d111a] text-white">
                      Kustomisasi Manual (Custom Checklist)
                    </option>
                  </select>
                  <ChevronDown size={16} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/40 pointer-events-none" />
                </div>
              </div>

              {/* Checklist Items */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold uppercase tracking-wider text-white/70">
                    Checklist Komponen yang Akan di-Drop:
                  </label>
                  <span className="text-[11px] font-mono font-bold text-red-400">
                    {selectedItems.length} dari {FRESH_START_ITEMS.length} dipilih
                  </span>
                </div>

                <div className="flex flex-col gap-2">
                  {FRESH_START_ITEMS.map((item) => {
                    const isChecked = selectedItems.includes(item.id);
                    return (
                      <div
                        key={item.id}
                        onClick={() => toggleItem(item.id)}
                        className={`p-3 rounded-xl border transition-all cursor-pointer flex items-start gap-3 select-none ${
                          isChecked 
                            ? "bg-red-500/10 border-red-500/40 text-white shadow-sm" 
                            : "bg-white/[0.02] border-white/5 text-white/50 hover:border-white/10 hover:bg-white/[0.04]"
                        }`}
                      >
                        {/* Checkbox box */}
                        <div className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
                          isChecked 
                            ? "bg-red-500 border-red-500 text-white" 
                            : "border-white/20 bg-white/5"
                        }`}>
                          {isChecked && <Check size={14} strokeWidth={3} />}
                        </div>

                        {/* Text and badges */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className={`text-xs sm:text-sm font-semibold ${isChecked ? "text-white" : "text-white/60"}`}>
                              {item.label}
                            </span>
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-white/50 shrink-0">
                              {item.badge}
                            </span>
                          </div>
                          <p className="text-[11px] text-white/40 mt-0.5 leading-relaxed">
                            {item.description}
                          </p>
                          <span className="inline-block mt-1 font-mono text-[10px] text-red-400/80">
                            Tabel: {item.tableName}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Safety notice banner */}
              <div className="p-3 rounded-xl bg-brand-green/10 border border-brand-green/20 flex items-start gap-2.5 text-xs text-brand-green/90">
                <ShieldCheck size={16} className="shrink-0 mt-0.5 text-brand-green" />
                <p className="leading-relaxed">
                  <strong>Aman:</strong> Data candlestick historis (<code className="font-mono text-[11px]">market_data_merged</code>) dan kalender makro <span className="underline">TIDAK AKAN</span> dihapus sehingga AI tetap memiliki basis teknikal yang lengkap.
                </p>
              </div>

            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-white/10 bg-white/[0.02] flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                disabled={isResetting}
                className="py-2.5 px-4 rounded-xl text-xs font-semibold text-white/70 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
              >
                Batal
              </button>
              
              <button
                type="button"
                onClick={handleConfirmReset}
                disabled={isResetting || selectedItems.length === 0}
                className="py-2.5 px-5 rounded-xl text-xs font-bold uppercase tracking-wider flex items-center gap-2 bg-gradient-to-r from-red-600 to-red-500 hover:from-red-500 hover:to-red-400 text-white shadow-lg shadow-red-600/30 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Trash2 size={14} className={isResetting ? "animate-spin" : ""} />
                {isResetting ? "MENGHAPUS DATA..." : `DROP ${selectedItems.length} KOMPONEN`}
              </button>
            </div>

          </div>
        </div>
      )}
    </div>
  );
}
