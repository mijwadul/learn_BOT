"use client";

import { useState } from "react";
import { Settings2, ShieldAlert, Zap } from "lucide-react";

export default function StrategiesPage() {
  const [loading, setLoading] = useState(false);
  const [lastAction, setLastAction] = useState<string | null>(null);

  const forceMode = async (mode: string, action: "force_live" | "quarantine") => {
    setLoading(true);
    try {
      const endpoint = action === "force_live" ? "/api/strategies/force_live" : "/api/strategies/quarantine";
      const res = await fetch(`http://localhost:8000${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode })
      });
      const data = await res.json();
      setLastAction(`Successfully applied [${action.toUpperCase()}] to ${mode.toUpperCase()} mode. System state is now: ${data.state}`);
    } catch (err) {
      setLastAction(`Error: Failed to connect to backend.`);
    }
    setLoading(false);
  };

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="mb-8">
        <h1 className="text-3xl font-black text-white tracking-widest flex items-center gap-3">
          <Settings2 className="text-brand-green" /> STRATEGIES
        </h1>
        <p className="text-white/50 mt-2">Manage execution modes and manual overrides (Phase 3)</p>
      </div>

      {lastAction && (
        <div className="mb-6 p-4 rounded-xl bg-brand-blue/20 border border-brand-blue/50 text-brand-blue font-medium">
          {lastAction}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Normal Mode (Scalping) */}
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div>
            <h2 className="text-xl font-bold text-white mb-2">Normal Mode (Scalping)</h2>
            <p className="text-sm text-white/50 mb-6">Aggressive intraday trading. Optimized on H1 data.</p>
          </div>
          <div className="flex gap-4">
            <button 
              disabled={loading}
              onClick={() => forceMode("normal", "force_live")}
              className="flex-1 bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/50 p-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all"
            >
              <Zap size={20} /> Force LIVE
            </button>
            <button 
              disabled={loading}
              onClick={() => forceMode("normal", "quarantine")}
              className="flex-1 bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/50 p-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all"
            >
              <ShieldAlert size={20} /> Quarantine
            </button>
          </div>
        </div>

        {/* Runner Mode (Trend) */}
        <div className="glass-panel p-6 flex flex-col justify-between">
          <div>
            <h2 className="text-xl font-bold text-white mb-2">Runner Mode (Trend)</h2>
            <p className="text-sm text-white/50 mb-6">Long term position holding. Optimized on full H4 data.</p>
          </div>
          <div className="flex gap-4">
            <button 
              disabled={loading}
              onClick={() => forceMode("runner", "force_live")}
              className="flex-1 bg-brand-green/20 hover:bg-brand-green/30 text-brand-green border border-brand-green/50 p-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all"
            >
              <Zap size={20} /> Force LIVE
            </button>
            <button 
              disabled={loading}
              onClick={() => forceMode("runner", "quarantine")}
              className="flex-1 bg-brand-red/20 hover:bg-brand-red/30 text-brand-red border border-brand-red/50 p-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all"
            >
              <ShieldAlert size={20} /> Quarantine
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
