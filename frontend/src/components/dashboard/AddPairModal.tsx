"use client";

import React from "react";
import { Plus } from "lucide-react";

interface AddPairModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddPair: (e: React.FormEvent) => void;
  newPairInput: string;
  setNewPairInput: (val: string) => void;
  isAddingPair: boolean;
}

export const AddPairModal: React.FC<AddPairModalProps> = ({
  isOpen,
  onClose,
  onAddPair,
  newPairInput,
  setNewPairInput,
  isAddingPair,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-[#0b100e] border border-white/15 rounded-3xl p-6 w-full max-w-md shadow-2xl relative">
        <div className="flex items-center justify-between mb-4">
          <span className="text-base font-bold text-white flex items-center gap-2">
            <Plus size={18} className="text-cyan-400" /> Daftarkan Pair Baru
          </span>
          <button
            type="button"
            onClick={onClose}
            className="text-white/40 hover:text-white transition-colors cursor-pointer"
          >
            ✕
          </button>
        </div>

        <form onSubmit={onAddPair} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-white/60 mb-1.5">
              Symbol Pair (contoh: EURUSD, GBPUSD, USDJPY, BTCUSD)
            </label>
            <input
              type="text"
              value={newPairInput}
              onChange={(e) => setNewPairInput(e.target.value.toUpperCase())}
              placeholder="EURUSD"
              className="w-full bg-black/60 border border-white/15 rounded-xl px-3.5 py-2.5 text-white font-mono text-sm focus:border-cyan-400 outline-none uppercase"
              autoFocus
            />
            <p className="text-[11px] text-white/40 mt-1.5">
              Sistem otomatis mendeteksi suffix broker MT5 (contoh: EURUSDm, EURUSDc) dan mengatur model untuk pair ini.
            </p>
          </div>

          <div className="flex items-center justify-end gap-2.5 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-xl text-xs font-semibold text-white/60 hover:text-white bg-white/5 hover:bg-white/10 transition-all cursor-pointer"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={isAddingPair || !newPairInput.trim()}
              className="px-5 py-2 rounded-xl text-xs font-bold text-black bg-cyan-400 hover:bg-cyan-300 transition-all disabled:opacity-40 cursor-pointer shadow-lg shadow-cyan-500/20"
            >
              {isAddingPair ? "Mendaftarkan..." : "Daftarkan Pair"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
