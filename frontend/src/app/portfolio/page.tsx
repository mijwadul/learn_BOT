"use client";
import { useState, useEffect } from "react";
import { Wallet, ArrowUpRight, ArrowDownRight } from "lucide-react";

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState({ value: 0, equity: 0, open_positions: [] as any[] });

  useEffect(() => {
    const fetchPortfolio = () => {
      fetch("http://localhost:8000/api/state")
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

  const formatCurrency = (val: number) => {
    return (val || 0).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const profit = portfolio.equity - portfolio.value;
  const isProfit = profit >= 0;

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
          <p className="text-4xl font-black text-white" suppressHydrationWarning>
            ${formatCurrency(portfolio.value)}
          </p>
        </div>
        <div className="glass-panel p-6">
          <p className="text-white/50 text-sm font-semibold uppercase tracking-wider mb-2">Floating Profit/Loss</p>
          <p
            className={`text-4xl font-black flex items-center gap-2 ${isProfit ? 'text-brand-green' : 'text-brand-red'}`}
            suppressHydrationWarning
          >
            {isProfit ? '+' : ''}${formatCurrency(profit)}
            {isProfit ? <ArrowUpRight size={28} /> : <ArrowDownRight size={28} />}
          </p>
        </div>
        <div className="glass-panel p-6">
          <p className="text-white/50 text-sm font-semibold uppercase tracking-wider mb-2">Equity</p>
          <p className="text-4xl font-black text-white" suppressHydrationWarning>
            ${formatCurrency(portfolio.equity)}
          </p>
        </div>
      </div>

      <h2 className="text-lg font-bold text-white mb-4">Open Positions ({portfolio.open_positions.length})</h2>
      <div className="glass-panel flex-1 overflow-hidden flex flex-col">
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
    </div>
  );
}
