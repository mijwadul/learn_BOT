import { Wallet, ArrowUpRight, ArrowDownRight } from "lucide-react";

export default function PortfolioPage() {
  return (
    <div className="p-6 h-full flex flex-col">
      <div className="mb-8">
        <h1 className="text-3xl font-black text-white tracking-widest flex items-center gap-3">
          <Wallet className="text-brand-green" /> PORTFOLIO
        </h1>
        <p className="text-white/50 mt-2">Live overview of your assets and open positions</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <div className="glass-panel p-6">
          <p className="text-white/50 text-sm font-semibold uppercase tracking-wider mb-2">Total Balance</p>
          <p className="text-4xl font-black text-white">$10,450.00</p>
        </div>
        <div className="glass-panel p-6">
          <p className="text-white/50 text-sm font-semibold uppercase tracking-wider mb-2">Daily Profit</p>
          <p className="text-4xl font-black text-brand-green flex items-center gap-2">
            +$1,245.80 <ArrowUpRight size={28} />
          </p>
        </div>
        <div className="glass-panel p-6">
          <p className="text-white/50 text-sm font-semibold uppercase tracking-wider mb-2">Margin Level</p>
          <p className="text-4xl font-black text-white">450.2%</p>
        </div>
      </div>

      <h2 className="text-lg font-bold text-white mb-4">Open Positions (Mocked)</h2>
      <div className="glass-panel flex-1 overflow-hidden flex flex-col">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-white/10 text-white/50 text-xs uppercase tracking-wider">
                <th className="p-4 font-medium">Symbol</th>
                <th className="p-4 font-medium">Type</th>
                <th className="p-4 font-medium">Volume</th>
                <th className="p-4 font-medium">Open Price</th>
                <th className="p-4 font-medium">Current Price</th>
                <th className="p-4 font-medium text-right">Profit</th>
              </tr>
            </thead>
            <tbody className="text-sm">
              <tr className="border-b border-white/5 hover:bg-white/5 transition-colors">
                <td className="p-4 font-bold text-white">XAUUSD</td>
                <td className="p-4 text-brand-green font-bold">BUY</td>
                <td className="p-4 text-white/70">0.50</td>
                <td className="p-4 text-white/70">2021.45</td>
                <td className="p-4 text-white/70">2025.10</td>
                <td className="p-4 text-right font-bold text-brand-green">+$182.50</td>
              </tr>
              <tr className="hover:bg-white/5 transition-colors">
                <td className="p-4 font-bold text-white">EURUSD</td>
                <td className="p-4 text-brand-red font-bold">SELL</td>
                <td className="p-4 text-white/70">1.00</td>
                <td className="p-4 text-white/70">1.09450</td>
                <td className="p-4 text-white/70">1.09520</td>
                <td className="p-4 text-right font-bold text-brand-red">-$70.00</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
