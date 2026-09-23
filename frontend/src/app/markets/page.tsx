import { LineChart } from "lucide-react";

export default function MarketsPage() {
  return (
    <div className="p-3 sm:p-4 md:p-6 min-h-full flex flex-col">
      <div className="mb-6 md:mb-8">
        <h1 className="text-2xl sm:text-3xl font-black text-white tracking-widest flex items-center gap-2 sm:gap-3">
          <LineChart className="text-brand-green" /> MARKETS
        </h1>
        <p className="text-white/50 text-xs sm:text-sm mt-1">Market screener and symbol selection</p>
      </div>

      <div className="flex-1 glass-panel flex flex-col items-center justify-center text-center p-6">
        <LineChart size={64} className="text-white/10 mb-6" />
        <h2 className="text-2xl font-bold text-white mb-2">Multi-Symbol Screener</h2>
        <p className="text-white/40 max-w-md">
          This module is reserved for Phase 4: Dynamic Symbol switching. Currently, the bot operates solely on the symbol defined in Config.SYMBOL (XAUUSD).
        </p>
      </div>
    </div>
  );
}
