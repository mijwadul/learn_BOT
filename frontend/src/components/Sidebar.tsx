"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  LayoutDashboard, 
  Wallet, 
  LineChart, 
  Settings2, 
  Terminal
} from "lucide-react";

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="w-20 md:w-64 border-r border-white/10 flex flex-col items-center md:items-start py-6 px-4 shrink-0 bg-brand-dark/50 backdrop-blur-md">
      <div className="mb-10 w-full flex justify-center md:justify-start items-center gap-3">
        <div className="w-10 h-10 rounded-lg bg-brand-blue flex items-center justify-center font-bold text-white shrink-0">
          AG
        </div>
        <div className="hidden md:block">
          <h1 className="font-bold tracking-wider text-sm leading-tight text-white/90">AVANTGARDE</h1>
          <p className="text-xs text-white/50 uppercase tracking-widest">Trading</p>
        </div>
      </div>

      <nav className="flex-1 w-full space-y-4">
        <NavItem href="/" icon={<LayoutDashboard size={22} />} label="Dashboard" active={pathname === "/"} />
        <NavItem href="/portfolio" icon={<Wallet size={22} />} label="Portfolio" active={pathname === "/portfolio"} />
        <NavItem href="/markets" icon={<LineChart size={22} />} label="Markets" active={pathname === "/markets"} />
        <NavItem href="/strategies" icon={<Settings2 size={22} />} label="Strategies" active={pathname === "/strategies"} />
        <NavItem href="/logs" icon={<Terminal size={22} />} label="Logs" active={pathname === "/logs"} />
      </nav>
    </div>
  );
}

function NavItem({ href, icon, label, active = false }: { href: string, icon: React.ReactNode, label: string, active?: boolean }) {
  return (
    <Link href={href} className={`w-full flex flex-col md:flex-row items-center md:justify-start gap-2 md:gap-4 p-3 rounded-xl transition-all duration-200 ${active ? 'bg-brand-green/20 text-brand-green glow-green' : 'text-white/40 hover:text-white/90 hover:bg-white/5'}`}>
      {icon}
      <span className="text-xs md:text-sm font-semibold">{label}</span>
    </Link>
  );
}
