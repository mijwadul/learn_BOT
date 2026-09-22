import { Terminal as TerminalIcon } from "lucide-react";

export default function LogsPage() {
  return (
    <div className="p-6 h-full flex flex-col">
      <div className="mb-8">
        <h1 className="text-3xl font-black text-white tracking-widest flex items-center gap-3">
          <TerminalIcon className="text-brand-green" /> SYSTEM LOGS
        </h1>
        <p className="text-white/50 mt-2">Real-time terminal output from backend agents</p>
      </div>

      <div className="flex-1 bg-black/80 rounded-xl border border-white/10 p-4 font-mono text-xs md:text-sm text-green-400 overflow-y-auto">
        <div className="space-y-2 opacity-80">
          <p>[2026-09-22 10:45:01] INFO: SupervisorAgent started.</p>
          <p>[2026-09-22 10:45:02] INFO: MT5 Initialized Successfully.</p>
          <p>[2026-09-22 10:45:02] INFO: DataMinerAgent bound to XAUUSD.</p>
          <p>[2026-09-22 10:45:05] WARN: [SEKRING] Waiting for manual override or valid condition.</p>
          <p className="text-white/50 italic mt-4">-- WebSocket connection for live logs pending --</p>
        </div>
      </div>
    </div>
  );
}
