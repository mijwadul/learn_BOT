"use client";

import React, { useState } from "react";
import { AlertTriangle, X, Check, ChevronDown, Trash2 } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";

export interface FreshStartOption {
  id: string;
  label: string;
  tableName: string;
  description: string;
  badge: string;
}

export const FRESH_START_ITEMS: FreshStartOption[] = [
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

interface FreshStartModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function FreshStartModal({ isOpen, onClose, onSuccess }: FreshStartModalProps) {
  const toast = useToast();
  const [selectedItems, setSelectedItems] = useState<string[]>(FRESH_START_ITEMS.map((i) => i.id));
  const [preset, setPreset] = useState<string>("all");
  const [isResetting, setIsResetting] = useState(false);

  if (!isOpen) return null;

  const handlePresetChange = (value: string) => {
    setPreset(value);
    if (value === "all") {
      setSelectedItems(FRESH_START_ITEMS.map((i) => i.id));
    } else if (value === "trades_only") {
      setSelectedItems(["trade_logs", "journal"]);
    } else if (value === "ai_only") {
      setSelectedItems(["decision_samples", "rlhf_setups", "hard_negatives"]);
    }
  };

  const toggleItem = (id: string) => {
    let next: string[];
    if (selectedItems.includes(id)) {
      next = selectedItems.filter((item) => item !== id);
    } else {
      next = [...selectedItems, id];
    }
    setSelectedItems(next);

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
      toast.warning("Pilih minimal satu komponen data untuk di-drop.", "Pilihan Kosong");
      return;
    }

    setIsResetting(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/trades/reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ categories: selectedItems }),
      });
      const data = await res.json();
      if (data.status === "success") {
        toast.success("Komponen data yang dipilih telah berhasil di-drop. Sistem siap untuk Fresh Start.", "Fresh Start Berhasil");
        onClose();
        if (onSuccess) onSuccess();
      } else {
        toast.error("Gagal mereset: " + (data.message || "Unknown error"), "Gagal Reset");
      }
    } catch (err) {
      toast.error("Gagal terhubung ke backend server.", "Error Jaringan");
    } finally {
      setIsResetting(false);
    }
  };

  return (
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
            onClick={() => !isResetting && onClose()}
            className="text-white/40 hover:text-white p-1.5 rounded-lg hover:bg-white/5 transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-4 sm:p-5 overflow-y-auto flex flex-col gap-4 flex-1">
          {/* Preset Selector */}
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
                    <div className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
                      isChecked ? "bg-red-500 border-red-500 text-white" : "border-white/20 bg-white/5"
                    }`}>
                      {isChecked && <Check size={14} className="stroke-[3]" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs sm:text-sm font-bold text-white tracking-wide">{item.label}</span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-white/10 text-white/70 border border-white/10">
                          {item.badge}
                        </span>
                      </div>
                      <p className="text-[11px] text-white/50 mt-0.5 leading-snug">{item.description}</p>
                      <span className="text-[10px] font-mono text-red-400/80 mt-1 block">Tabel: {item.tableName}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-white/10 flex items-center justify-end gap-3 bg-[#0a0d14]">
          <button
            onClick={() => !isResetting && onClose()}
            disabled={isResetting}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-white/60 hover:text-white hover:bg-white/5 border border-white/10 transition-colors cursor-pointer"
          >
            Batal
          </button>
          <button
            onClick={handleConfirmReset}
            disabled={isResetting || selectedItems.length === 0}
            className="px-5 py-2 rounded-xl text-xs font-bold text-white bg-red-600 hover:bg-red-500 shadow-lg shadow-red-900/50 flex items-center gap-2 transition-all cursor-pointer disabled:opacity-50"
          >
            {isResetting ? (
              <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <Trash2 size={14} />
            )}
            Drop ({selectedItems.length}) Data Terpilih
          </button>
        </div>
      </div>
    </div>
  );
}
