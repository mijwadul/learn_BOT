"use client";

import React, { useState, useEffect } from "react";
import { Sliders, DollarSign, Percent, Check, Loader2 } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";

interface RiskManagementCardProps {
  portfolioEquity?: number;
}

export function RiskManagementCard({ portfolioEquity = 1000 }: RiskManagementCardProps) {
  const toast = useToast();
  const [riskMode, setRiskMode] = useState<"dollars" | "percent">("dollars");
  const [riskDollars, setRiskDollars] = useState(10.0);
  const [riskPercent, setRiskPercent] = useState(1.0);
  const [isSavingRisk, setIsSavingRisk] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    fetch(`${getApiBaseUrl()}/api/settings/risk`)
      .then((res) => res.json())
      .then((data) => {
        if (data.risk_mode) setRiskMode(data.risk_mode);
        if (data.max_risk_dollars !== undefined) setRiskDollars(data.max_risk_dollars);
        if (data.max_risk_percent !== undefined) setRiskPercent(data.max_risk_percent);
      })
      .catch((err) => console.error("Failed to load risk settings", err));
  }, []);

  const effectiveRiskDollars =
    riskMode === "dollars"
      ? riskDollars
      : ((portfolioEquity > 0 ? portfolioEquity : 1000) * riskPercent) / 100;

  const handleSaveRisk = async () => {
    setIsSavingRisk(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/settings/risk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          risk_mode: riskMode,
          max_risk_dollars: riskDollars,
          max_risk_percent: riskPercent,
        }),
      });
      if (res.ok) {
        setSaveSuccess(true);
        toast.success(`Batas risiko berhasil diperbarui: $${effectiveRiskDollars.toFixed(2)}`, "Pengaturan Disimpan");
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
    <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl relative overflow-hidden mb-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-brand-green/10 text-brand-green border border-brand-green/20">
            <Sliders size={18} />
          </div>
          <div>
            <h3 className="text-base font-bold text-white tracking-wide">Risk Management & Lot Sizing</h3>
            <p className="text-xs text-white/50">Toleransi batas kerugian maksimal per transaksi OP</p>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-white/5 p-1 rounded-xl border border-white/10">
          <button
            type="button"
            onClick={() => setRiskMode("dollars")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
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
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
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

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-center">
        {/* Input Sizing */}
        <div className="sm:col-span-2 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          {riskMode === "dollars" ? (
            <div className="flex-1 relative">
              <label className="text-[11px] font-bold text-white/40 uppercase block mb-1">Max Risk Per Trade ($)</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 font-bold">$</span>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={riskDollars}
                  onChange={(e) => setRiskDollars(Math.max(1, parseFloat(e.target.value) || 1))}
                  className="w-full bg-white/5 border border-white/10 rounded-xl py-2 pl-8 pr-3 text-white font-bold text-sm focus:outline-none focus:border-brand-green/50"
                />
              </div>
            </div>
          ) : (
            <div className="flex-1 relative">
              <label className="text-[11px] font-bold text-white/40 uppercase block mb-1">Max Risk Per Trade (%)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.1"
                  min="0.1"
                  max="10.0"
                  value={riskPercent}
                  onChange={(e) => setRiskPercent(Math.max(0.1, parseFloat(e.target.value) || 0.1))}
                  className="w-full bg-white/5 border border-white/10 rounded-xl py-2 pl-3 pr-8 text-white font-bold text-sm focus:outline-none focus:border-brand-green/50"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 font-bold">%</span>
              </div>
            </div>
          )}

          {/* Effective Value Display */}
          <div className="flex-1 bg-white/[0.02] border border-white/5 rounded-xl p-2.5 flex flex-col justify-center">
            <span className="text-[10px] text-white/40 font-bold uppercase">Estimasi Risiko Nominal:</span>
            <div className="text-sm font-black text-brand-green">
              ${effectiveRiskDollars.toFixed(2)}{" "}
              <span className="text-[10px] text-white/40 font-normal">
                (dari equity ${portfolioEquity.toFixed(2)})
              </span>
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end">
          <button
            onClick={handleSaveRisk}
            disabled={isSavingRisk}
            className={`w-full sm:w-auto px-5 py-2.5 rounded-xl font-bold text-xs flex items-center justify-center gap-2 transition-all ${
              saveSuccess
                ? "bg-brand-green text-black"
                : "bg-white/10 hover:bg-white/20 text-white border border-white/10"
            }`}
          >
            {isSavingRisk ? (
              <Loader2 className="animate-spin w-4 h-4" />
            ) : saveSuccess ? (
              <Check className="w-4 h-4" />
            ) : null}
            {saveSuccess ? "Tersimpan!" : "Terapkan Aturan Risiko"}
          </button>
        </div>
      </div>
    </div>
  );
}
