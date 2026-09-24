"use client";

import React, { useState, useEffect } from "react";
import { Sliders, DollarSign, Percent, Check, Loader2, Layers, ShieldCheck, AlertCircle } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";

interface RiskManagementCardProps {
  portfolioEquity?: number;
}

export function RiskManagementCard({ portfolioEquity = 1000 }: RiskManagementCardProps) {
  const toast = useToast();
  const [riskMode, setRiskMode] = useState<"fixed" | "dollars" | "percent">("fixed");
  const [fixedLotSize, setFixedLotSize] = useState(0.01);
  const [riskDollars, setRiskDollars] = useState(10.0);
  const [riskPercent, setRiskPercent] = useState(1.0);
  const [maxLotCap, setMaxLotCap] = useState(0.10);
  const [isCentAccount, setIsCentAccount] = useState(false);
  const [activeSymbol, setActiveSymbol] = useState("XAUUSD");
  const [isSavingRisk, setIsSavingRisk] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    // 1. Fetch risk settings
    fetch(`${getApiBaseUrl()}/api/settings/risk`)
      .then((res) => res.json())
      .then((data) => {
        if (data.risk_mode) setRiskMode(data.risk_mode);
        if (data.fixed_lot_size !== undefined) setFixedLotSize(data.fixed_lot_size);
        if (data.max_risk_dollars !== undefined) setRiskDollars(data.max_risk_dollars);
        if (data.max_risk_percent !== undefined) setRiskPercent(data.max_risk_percent);
        if (data.max_lot_cap !== undefined) setMaxLotCap(data.max_lot_cap);
      })
      .catch((err) => console.error("Failed to load risk settings", err));

    // 2. Fetch symbol from state
    fetch(`${getApiBaseUrl()}/api/state`)
      .then((res) => res.json())
      .then((data) => {
        if (data.active_symbol) {
          setActiveSymbol(data.active_symbol);
          if (data.active_symbol.toLowerCase().endsWith("c")) {
            setIsCentAccount(true);
          }
        }
      })
      .catch((err) => console.error("Failed to load state for symbol", err));
  }, []);

  const effectiveRiskDollars =
    riskMode === "dollars"
      ? riskDollars
      : riskMode === "percent"
      ? ((portfolioEquity > 0 ? portfolioEquity : 1000) * riskPercent) / 100
      : null;

  const handleSaveRisk = async () => {
    setIsSavingRisk(true);
    try {
      const payload: {
        risk_mode: string;
        max_lot_cap: number;
        fixed_lot_size?: number;
        max_risk_dollars?: number;
        max_risk_percent?: number;
      } = {
        risk_mode: riskMode,
        max_lot_cap: maxLotCap,
      };

      if (riskMode === "fixed") {
        payload.fixed_lot_size = fixedLotSize;
      } else if (riskMode === "dollars") {
        payload.max_risk_dollars = riskDollars;
      } else if (riskMode === "percent") {
        payload.max_risk_percent = riskPercent;
      }

      const res = await fetch(`${getApiBaseUrl()}/api/settings/risk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setSaveSuccess(true);
        const modeDesc =
          riskMode === "fixed"
            ? `Fixed ${fixedLotSize.toFixed(2)} Lot`
            : riskMode === "dollars"
            ? `Max $${riskDollars.toFixed(2)} per OP`
            : `Max ${riskPercent}% per OP`;
        toast.success(`Aturan Lot Sizing & Risiko diperbarui: ${modeDesc} (Max Cap: ${maxLotCap} Lot)`, "Pengaturan Disimpan");
        setTimeout(() => setSaveSuccess(false), 2500);
      } else {
        toast.error("Gagal memperbarui pengaturan risiko.", "Gagal");
      }
    } catch (err) {
      toast.error("Error: Gagal terhubung ke backend server.", "Koneksi Gagal");
    } finally {
      setIsSavingRisk(false);
    }
  };

  return (
    <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl relative mb-6">
      {/* Header and Mode Selector */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 mb-5">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-brand-green/10 text-brand-green border border-brand-green/20">
            <Sliders size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white tracking-wide">Risk Management &amp; Lot Sizing</h3>
              {isCentAccount && (
                <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30">
                  Cent Account ({activeSymbol})
                </span>
              )}
            </div>
            <p className="text-xs text-white/50">Pilih model perhitungan ukuran lot dan batas risiko per transaksi</p>
          </div>
        </div>

        {/* 3 Sizing Modes */}
        <div className="flex items-center gap-1.5 bg-white/5 p-1 rounded-xl border border-white/10 self-stretch sm:self-auto overflow-x-auto">
          <button
            type="button"
            onClick={() => setRiskMode("fixed")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
              riskMode === "fixed"
                ? "bg-brand-green text-black shadow-md shadow-brand-green/30"
                : "text-white/60 hover:text-white"
            }`}
          >
            <Layers size={14} />
            Lot Tetap (Fixed)
          </button>
          <button
            type="button"
            onClick={() => setRiskMode("dollars")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
              riskMode === "dollars"
                ? "bg-brand-green text-black shadow-md shadow-brand-green/30"
                : "text-white/60 hover:text-white"
            }`}
          >
            <DollarSign size={14} />
            Dollar Tetap ($)
          </button>
          <button
            type="button"
            onClick={() => setRiskMode("percent")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
              riskMode === "percent"
                ? "bg-brand-green text-black shadow-md shadow-brand-green/30"
                : "text-white/60 hover:text-white"
            }`}
          >
            <Percent size={14} />
            Persen Modal (%)
          </button>
        </div>
      </div>

      {/* Inputs & Parameters Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
        {/* Dynamic Mode Input */}
        {riskMode === "fixed" && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-3">
            <label className="text-[11px] font-bold text-white/60 uppercase block mb-1">
              Ukuran Lot Tetap (Lot Size)
            </label>
            <div className="relative">
              <input
                type="number"
                step="0.01"
                min="0.01"
                max={maxLotCap}
                value={fixedLotSize}
                onChange={(e) => setFixedLotSize(Math.max(0.01, parseFloat(e.target.value) || 0.01))}
                className="w-full bg-black/40 border border-white/10 rounded-lg py-2 px-3 text-white font-mono font-bold text-sm focus:outline-none focus:border-brand-green"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 text-xs font-mono">LOT</span>
            </div>
            <p className="text-[10px] text-white/40 mt-1">Setiap OP menggunakan lot ini tanpa kalkulasi dinamis.</p>
          </div>
        )}

        {riskMode === "dollars" && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-3">
            <label className="text-[11px] font-bold text-white/60 uppercase block mb-1">
              Batas Toleransi Rugi ($)
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 font-bold">$</span>
              <input
                type="number"
                step="1"
                min="1"
                value={riskDollars}
                onChange={(e) => setRiskDollars(Math.max(1, parseFloat(e.target.value) || 1))}
                className="w-full bg-black/40 border border-white/10 rounded-lg py-2 pl-8 pr-3 text-white font-mono font-bold text-sm focus:outline-none focus:border-brand-green"
              />
            </div>
            <p className="text-[10px] text-white/40 mt-1">Lot dihitung agar kerugian menyentuh SL = nominal ini.</p>
          </div>
        )}

        {riskMode === "percent" && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-3">
            <label className="text-[11px] font-bold text-white/60 uppercase block mb-1">
              Batas Toleransi Rugi (%)
            </label>
            <div className="relative">
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="10.0"
                value={riskPercent}
                onChange={(e) => setRiskPercent(Math.max(0.1, parseFloat(e.target.value) || 0.1))}
                className="w-full bg-black/40 border border-white/10 rounded-lg py-2 pl-3 pr-8 text-white font-mono font-bold text-sm focus:outline-none focus:border-brand-green"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 font-bold">%</span>
            </div>
            <p className="text-[10px] text-white/40 mt-1">Lot dihitung adaptif berdasarkan persentase ekuitas akun.</p>
          </div>
        )}

        {/* Max Lot Safety Cap */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-3">
          <div className="flex items-center justify-between mb-1">
            <label className="text-[11px] font-bold text-amber-400 uppercase flex items-center gap-1">
              <ShieldCheck size={13} /> Max Lot Safety Cap
            </label>
            <span className="text-[10px] text-white/40">Fat-Finger Protection</span>
          </div>
          <div className="relative">
            <input
              type="number"
              step="0.01"
              min="0.01"
              max="5.0"
              value={maxLotCap}
              onChange={(e) => setMaxLotCap(Math.max(0.01, parseFloat(e.target.value) || 0.01))}
              className="w-full bg-black/40 border border-amber-500/30 rounded-lg py-2 px-3 text-white font-mono font-bold text-sm focus:outline-none focus:border-amber-400"
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 text-xs font-mono">MAX LOT</span>
          </div>
          <p className="text-[10px] text-white/40 mt-1">Batas plafon mutlak agar bot tidak pernah membuka lot lebih besar dari ini.</p>
        </div>

        {/* Summary Telemetry */}
        <div className="bg-white/[0.03] border border-white/5 rounded-xl p-3 flex flex-col justify-between font-mono tabular-nums">
          <span className="text-[10px] text-white/40 font-bold uppercase font-sans">Estimasi Penerapan:</span>
          {riskMode === "fixed" ? (
            <div className="text-sm font-black text-brand-green">
              {fixedLotSize.toFixed(2)} Lot <span className="text-[10px] text-white/50 font-normal font-sans">(Order Presisi Tetap)</span>
            </div>
          ) : (
            <div className="text-sm font-black text-brand-green">
              ${effectiveRiskDollars?.toFixed(2)}{" "}
              <span className="text-[10px] text-white/50 font-normal font-sans">
                (dari equity ${portfolioEquity.toFixed(2)})
              </span>
            </div>
          )}
          <div className="text-[10px] text-white/40 font-sans mt-1">
            Plafon Eksekusi: <span className="text-white font-mono font-bold">{maxLotCap.toFixed(2)} Lot</span>
          </div>
        </div>
      </div>

      {/* Note for Cent Account */}
      {isCentAccount && (
        <div className="mb-4 p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center gap-2 text-xs text-amber-300">
          <AlertCircle size={15} className="shrink-0" />
          <span>
            <strong>Informasi Akun Cent:</strong> Simbol <code>{activeSymbol}</code> bertransaksi dalam satuan Cent (USC). Nilai 100 USC setara dengan $1.00 USD. Penggunaan <strong>Lot Tetap 0.01</strong> sangat disarankan untuk stabilitas modal kecil.
          </span>
        </div>
      )}

      {/* Save Button */}
      <div className="flex justify-end pt-2 border-t border-white/5">
        <button
          onClick={handleSaveRisk}
          disabled={isSavingRisk}
          className={`px-6 py-2.5 rounded-xl font-bold text-xs flex items-center gap-2 transition-all cursor-pointer ${
            saveSuccess
              ? "bg-brand-green text-black shadow-lg shadow-brand-green/30"
              : "bg-white/10 hover:bg-brand-green hover:text-black text-white border border-white/10"
          }`}
        >
          {isSavingRisk ? (
            <Loader2 className="animate-spin w-4 h-4" />
          ) : saveSuccess ? (
            <Check className="w-4 h-4" />
          ) : null}
          {saveSuccess ? "Berhasil Disimpan!" : "Simpan & Terapkan Aturan Risiko"}
        </button>
      </div>
    </div>
  );
}
