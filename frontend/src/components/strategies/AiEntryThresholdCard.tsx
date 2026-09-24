"use client";

import React, { useState, useEffect } from "react";
import { Crosshair, Check, Loader2, Zap, ShieldAlert, Sparkles, AlertCircle } from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";

export function AiEntryThresholdCard() {
  const toast = useToast();
  const [threshold, setThreshold] = useState(75.0);
  const [initialThreshold, setInitialThreshold] = useState(75.0);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    fetch(`${getApiBaseUrl()}/api/settings/risk`)
      .then((res) => res.json())
      .then((data) => {
        if (data.ai_entry_threshold !== undefined) {
          setThreshold(data.ai_entry_threshold);
          setInitialThreshold(data.ai_entry_threshold);
        }
      })
      .catch((err) => console.error("Gagal memuat AI Entry Threshold:", err));
  }, []);

  const handleSaveThreshold = async () => {
    setIsSaving(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/settings/risk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ai_entry_threshold: threshold,
        }),
      });

      if (res.ok) {
        setSaveSuccess(true);
        setInitialThreshold(threshold);
        toast.success(
          `AI Entry Threshold berhasil disimpan: ${threshold}% (Hanya sinyal probabilitas ≥ ${threshold}% yang akan dieksekusi)`,
          "Threshold Disimpan"
        );
        setTimeout(() => setSaveSuccess(false), 2500);
      } else {
        toast.error("Gagal menyimpan AI Entry Threshold.", "Gagal");
      }
    } catch {
      toast.error("Koneksi gagal ke backend server.", "Error");
    } finally {
      setIsSaving(false);
    }
  };

  const getProfileBadge = () => {
    if (threshold < 65) {
      return {
        label: "Agresif (High Frequency)",
        desc: "Menerima banyak sinyal re-entry, namun rentan false breakout saat pasar choppy.",
        badgeClass: "bg-rose-500/10 text-rose-400 border-rose-500/30",
        icon: <Zap size={14} className="text-rose-400" />,
      };
    }
    if (threshold <= 79) {
      return {
        label: "Optimal / Balanced (Rekomendasi)",
        desc: "Keseimbangan ideal antara seleksi sinyal berkualitas tinggi dan frekuensi trade sehat.",
        badgeClass: "bg-brand-green/10 text-brand-green border-brand-green/30",
        icon: <Sparkles size={14} className="text-brand-green" />,
      };
    }
    return {
      label: "Konservatif (A++ Setup Only)",
      desc: "Hanya mengeksekusi sinyal berkonfluensi sempurna M1 + M5 + M15. Frekuensi trade rendah.",
      badgeClass: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
      icon: <ShieldAlert size={14} className="text-cyan-400" />,
    };
  };

  const profile = getProfileBadge();
  const hasChanges = threshold !== initialThreshold;

  return (
    <div className="bg-[#0b1210] border border-white/10 rounded-2xl p-5 shadow-xl relative mb-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-5">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <Crosshair size={18} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-white tracking-wide">AI Signal Entry Threshold</h3>
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${profile.badgeClass}`}>
                {profile.icon}
                {profile.label}
              </span>
            </div>
            <p className="text-xs text-white/50">
              Batas minimum probabilitas model LightGBM untuk menyetujui pembukaan posisi baru
            </p>
          </div>
        </div>

        {/* Current Value Display */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-xs text-white/40 block">Minimum Probabilitas</span>
            <span className="text-2xl font-black text-brand-green tracking-tight">
              {threshold.toFixed(0)}%
            </span>
          </div>
        </div>
      </div>

      {/* Main Slider & Presets */}
      <div className="bg-black/30 border border-white/5 rounded-xl p-4 mb-4">
        {/* Slider Controls */}
        <div className="mb-4">
          <div className="flex items-center justify-between text-xs text-white/60 mb-2">
            <span>50% (Sangat Longgar)</span>
            <span className="font-bold text-brand-green">Aktif: {threshold.toFixed(0)}% (Desimal: {(threshold / 100).toFixed(2)})</span>
            <span>90% (Sangat Ketat)</span>
          </div>
          <input
            type="range"
            min="50"
            max="90"
            step="1"
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            className="w-full accent-brand-green bg-white/10 h-2 rounded-lg cursor-pointer"
          />
        </div>

        {/* Preset Quick Buttons */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-white/5">
          <span className="text-[11px] font-bold text-white/40 mr-1">Preset Cepat:</span>
          {[
            { val: 60, label: "60% (Agresif)" },
            { val: 70, label: "70% (Moderat)" },
            { val: 75, label: "75% (Standar)" },
            { val: 80, label: "80% (Konservatif)" },
            { val: 85, label: "85% (Ultra)" },
          ].map((preset) => (
            <button
              key={preset.val}
              type="button"
              onClick={() => setThreshold(preset.val)}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
                threshold === preset.val
                  ? "bg-brand-green text-black font-bold shadow-md shadow-brand-green/20"
                  : "bg-white/5 hover:bg-white/10 text-white/70 hover:text-white border border-white/5"
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      {/* Explanatory Quant Note */}
      <div className="flex items-start gap-2.5 bg-white/[0.02] border border-white/5 rounded-xl p-3 mb-4 text-xs text-white/60 leading-relaxed">
        <AlertCircle size={16} className="text-cyan-400 shrink-0 mt-0.5" />
        <div>
          <span className="text-white/80 font-bold block mb-0.5">Penjelasan Operasional Executor:</span>
          {profile.desc} Saat AI mendeteksi probabilitas di bawah <span className="text-brand-green font-bold">{threshold}%</span>, order entry akan ditolak oleh Executor demi menjaga akurasi *Win Rate* akun.
        </div>
      </div>

      {/* Footer Save Action */}
      <div className="flex items-center justify-between pt-2">
        <span className="text-[11px] text-white/40">
          Parameter ini langsung sinkron ke file <code className="text-brand-green">config.py</code> dan Executor Agent secara *real-time*.
        </span>
        <button
          type="button"
          onClick={handleSaveThreshold}
          disabled={isSaving}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold transition-all shadow-lg ${
            saveSuccess
              ? "bg-emerald-500 text-black shadow-emerald-500/20"
              : hasChanges
              ? "bg-brand-green hover:bg-brand-green/90 text-black shadow-brand-green/20"
              : "bg-white/10 hover:bg-white/15 text-white/80"
          } disabled:opacity-50`}
        >
          {isSaving ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Menyimpan...
            </>
          ) : saveSuccess ? (
            <>
              <Check size={14} />
              Tersimpan!
            </>
          ) : (
            <>
              <Check size={14} />
              Simpan Threshold
            </>
          )}
        </button>
      </div>
    </div>
  );
}
