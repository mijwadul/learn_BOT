"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Image from "next/image";
import LogoImg from "./Logo.png";
import { 
  LayoutDashboard, 
  Wallet, 
  LineChart, 
  Settings2, 
  Terminal,
  BookOpen,
  Database,
  AlertOctagon,
  Menu,
  X
} from "lucide-react";

export default function Sidebar() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);

  const toggleSidebar = () => setIsOpen(!isOpen);
  const closeSidebar = () => setIsOpen(false);

  return (
    <>
      {/* Mobile Top Bar */}
      <div className="md:hidden flex items-center justify-between p-4 border-b border-white/10 bg-brand-dark/90 backdrop-blur-md fixed top-0 left-0 right-0 z-50">
        <div className="flex items-center gap-2">
          <Image src={LogoImg} alt="Avantgarde Logo" width={32} height={32} className="object-contain" />
          <h1 className="font-bold tracking-wider text-sm leading-tight text-white/90">BBMA AI</h1>
        </div>
        <button onClick={toggleSidebar} className="text-white/80 p-1 hover:text-white">
          {isOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Sidebar Content */}
      <div className={`fixed md:relative top-0 left-0 h-full z-40 transition-transform duration-300 transform ${isOpen ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0 w-64 border-r border-white/10 flex flex-col py-6 px-4 shrink-0 bg-brand-dark/95 md:bg-brand-dark/50 backdrop-blur-md pt-24 md:pt-6`}>
        
        <div className="hidden md:flex mb-10 w-full justify-start items-center gap-3">
          <div className="w-10 h-10 shrink-0 flex items-center justify-center">
            <Image src={LogoImg} alt="Avantgarde Logo" width={40} height={40} className="object-contain" />
          </div>
          <div>
            <h1 className="font-bold tracking-wider text-sm leading-tight text-white/90">BBMA AI</h1>
            <p className="text-xs text-white/50 uppercase tracking-widest">Trading Bot</p>
          </div>
        </div>

        <nav className="flex-1 w-full space-y-2 md:space-y-4 overflow-y-auto pr-2">
          <NavItem href="/" icon={<LayoutDashboard size={22} />} label="Dashboard" active={pathname === "/"} onClick={closeSidebar} />
          <NavItem href="/portfolio" icon={<Wallet size={22} />} label="Portfolio" active={pathname === "/portfolio"} onClick={closeSidebar} />
          <NavItem href="/markets" icon={<LineChart size={22} />} label="Markets" active={pathname === "/markets"} onClick={closeSidebar} />
          <NavItem href="/strategies" icon={<Settings2 size={22} />} label="Strategies" active={pathname === "/strategies"} onClick={closeSidebar} />
          <NavItem href="/database" icon={<Database size={22} />} label="Database" active={pathname === "/database"} onClick={closeSidebar} />
          <NavItem href="/journal" icon={<BookOpen size={22} />} label="Journal" active={pathname === "/journal"} onClick={closeSidebar} />
          <NavItem href="/logs" icon={<Terminal size={22} />} label="Logs" active={pathname === "/logs"} onClick={closeSidebar} />
        </nav>

        <div className="mt-auto w-full pt-4 border-t border-white/10 shrink-0">
          <button 
            onClick={async () => {
               if (confirm("Peringatan: Emergency Stop akan menghentikan seluruh eksekusi dan melikuidasi SEMUA posisi aktif! Lanjutkan?")) {
                 await fetch("http://localhost:8000/api/state/emergency", { method: "POST" });
                 alert("EMERGENCY STOP TRIGGERED! Cek logs untuk detail eksekusi.");
               }
            }}
            className="w-full flex items-center justify-center md:justify-start gap-2 p-3 rounded-xl bg-brand-red/20 text-brand-red hover:bg-brand-red/40 transition-colors font-bold"
          >
            <AlertOctagon size={22} className="shrink-0" />
            <span className="text-sm">Emergency Stop</span>
          </button>
        </div>
      </div>
      
      {/* Overlay for mobile */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/50 z-30 md:hidden" onClick={closeSidebar}></div>
      )}
    </>
  );
}

function NavItem({ href, icon, label, active = false, onClick }: { href: string, icon: React.ReactNode, label: string, active?: boolean, onClick: () => void }) {
  return (
    <Link href={href} onClick={onClick} className={`w-full flex flex-row items-center justify-start gap-4 p-3 rounded-xl transition-all duration-200 ${active ? 'bg-brand-green/20 text-brand-green glow-green' : 'text-white/40 hover:text-white/90 hover:bg-white/5'}`}>
      {icon}
      <span className="text-sm font-semibold">{label}</span>
    </Link>
  );
}
