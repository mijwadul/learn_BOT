"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Image from "next/image";
import LogoImg from "./Logo.png";
import { 
  LayoutDashboard, 
  Wallet, 
  LineChart, 
  Settings2, 
  BookOpen, 
  Database, 
  AlertOctagon, 
  Menu, 
  X, 
  PanelLeftClose, 
  PanelLeftOpen 
} from "lucide-react";
import { getApiBaseUrl } from "@/config";
import { useToast } from "@/components/ui/Toast";
import { ConfirmModal } from "@/components/ui/ConfirmModal";

export default function Sidebar() {
  const pathname = usePathname();
  const toast = useToast();
  const [isOpen, setIsOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isEmergencyModalOpen, setIsEmergencyModalOpen] = useState(false);
  const [isEmergencyLoading, setIsEmergencyLoading] = useState(false);

  // Restore collapsed state from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("bbma_sidebar_collapsed");
    if (saved !== null) {
      setIsCollapsed(saved === "true");
    }
  }, []);

  const toggleCollapse = () => {
    setIsCollapsed(prev => {
      const next = !prev;
      localStorage.setItem("bbma_sidebar_collapsed", String(next));
      return next;
    });
  };

  const toggleSidebar = () => setIsOpen(!isOpen);
  const closeSidebar = () => setIsOpen(false);

  const handleEmergencyStop = async () => {
    setIsEmergencyLoading(true);
    try {
      const res = await fetch(`${getApiBaseUrl()}/api/state/emergency`, { method: "POST" });
      if (res.ok) {
        toast.error("EMERGENCY STOP DIAKTIFKAN! Seluruh sistem dihentikan dan posisi aktif dilikuidasi.", "Emergency Stop");
      } else {
        toast.warning("Gagal memicu emergency stop di server.", "Gagal");
      }
    } catch (e) {
      toast.error("Tidak dapat terhubung ke backend server.", "Koneksi Gagal");
    } finally {
      setIsEmergencyLoading(false);
      setIsEmergencyModalOpen(false);
    }
  };

  return (
    <>
      {/* Mobile Top Bar */}
      <div className="md:hidden flex items-center justify-between p-4 border-b border-white/10 bg-brand-dark/90 backdrop-blur-md fixed top-0 left-0 right-0 z-50">
        <div className="flex items-center gap-2">
          <Image src={LogoImg} alt="Avantgarde Logo" width={32} height={32} className="object-contain" />
          <h1 className="font-bold tracking-wider text-sm leading-tight text-white/90">BBMA AI</h1>
        </div>
        <button onClick={toggleSidebar} className="text-white/80 p-1 hover:text-white" aria-label="Toggle Navigation">
          {isOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Sidebar Content */}
      <aside 
        className={`fixed md:relative top-0 left-0 h-full z-40 transition-all duration-300 ease-in-out ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        } md:translate-x-0 ${
          isCollapsed ? "md:w-[72px] md:px-2.5" : "md:w-64 md:px-4"
        } border-r border-white/10 flex flex-col py-6 px-4 shrink-0 bg-brand-dark/95 md:bg-brand-dark/50 backdrop-blur-md pt-20 md:pt-6 select-none`}
      >
        {/* Header / Logo + Collapse Toggle */}
        <div className={`hidden md:flex mb-8 w-full items-center ${isCollapsed ? "justify-center" : "justify-between"} gap-2`}>
          <Link href="/" className="flex items-center gap-3 overflow-hidden" title="BBMA AI Trading Bot">
            <div className="w-10 h-10 shrink-0 flex items-center justify-center">
              <Image src={LogoImg} alt="Avantgarde Logo" width={36} height={36} className="object-contain" />
            </div>
            {!isCollapsed && (
              <div className="transition-opacity duration-200 overflow-hidden whitespace-nowrap">
                <h1 className="font-bold tracking-wider text-sm leading-tight text-white/90">BBMA AI</h1>
                <p className="text-[10px] text-white/50 uppercase tracking-widest">Trading Bot</p>
              </div>
            )}
          </Link>

          {/* Sidebar Collapse Toggle */}
          <button
            onClick={toggleCollapse}
            className={`p-2 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors shrink-0 ${isCollapsed ? "mt-2" : ""}`}
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 w-full space-y-1.5 md:space-y-2 overflow-y-auto overflow-x-hidden pr-0.5 scrollbar-none">
          <NavItem href="/" icon={<LayoutDashboard size={22} />} label="Dashboard" active={pathname === "/"} isCollapsed={isCollapsed} onClick={closeSidebar} />
          <NavItem href="/portfolio" icon={<Wallet size={22} />} label="Portfolio" active={pathname === "/portfolio"} isCollapsed={isCollapsed} onClick={closeSidebar} />
          <NavItem href="/markets" icon={<LineChart size={22} />} label="Markets" active={pathname === "/markets"} isCollapsed={isCollapsed} onClick={closeSidebar} />
          <NavItem href="/strategies" icon={<Settings2 size={22} />} label="Strategies" active={pathname === "/strategies"} isCollapsed={isCollapsed} onClick={closeSidebar} />
          <NavItem href="/database" icon={<Database size={22} />} label="Database" active={pathname === "/database"} isCollapsed={isCollapsed} onClick={closeSidebar} />
          <NavItem href="/journal" icon={<BookOpen size={22} />} label="Journal" active={pathname === "/journal"} isCollapsed={isCollapsed} onClick={closeSidebar} />
        </nav>

        {/* Emergency Stop Button */}
        <div className="mt-auto w-full pt-4 border-t border-white/10 shrink-0">
          <button 
            onClick={() => setIsEmergencyModalOpen(true)}
            title="Emergency Stop"
            className={`w-full flex items-center ${isCollapsed ? "justify-center p-3" : "justify-center md:justify-start gap-2.5 p-3"} rounded-xl bg-brand-red/20 text-brand-red hover:bg-brand-red/40 transition-colors font-bold overflow-hidden`}
          >
            <AlertOctagon size={22} className="shrink-0 text-brand-red" />
            {!isCollapsed && <span className="text-xs sm:text-sm whitespace-nowrap">Emergency Stop</span>}
          </button>
        </div>
      </aside>
      
      {/* Overlay for mobile */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 md:hidden transition-opacity" onClick={closeSidebar}></div>
      )}

      {/* Emergency Stop Confirmation Modal (P1-4) */}
      <ConfirmModal
        isOpen={isEmergencyModalOpen}
        onClose={() => setIsEmergencyModalOpen(false)}
        onConfirm={handleEmergencyStop}
        title="Peringatan: Emergency Stop"
        description="Emergency Stop akan memutus siklus live trading, menghentikan bot secara instan, dan melikuidasi SELURUH posisi aktif di akun broker MT5. Tindakan ini tidak dapat dibatalkan."
        confirmText="Hentikan & Likuidasi"
        cancelText="Batal"
        variant="danger"
        isLoading={isEmergencyLoading}
      />
    </>
  );
}

function NavItem({ 
  href, 
  icon, 
  label, 
  active = false, 
  isCollapsed = false,
  onClick 
}: { 
  href: string; 
  icon: React.ReactNode; 
  label: string; 
  active?: boolean; 
  isCollapsed?: boolean;
  onClick: () => void;
}) {
  return (
    <Link 
      href={href} 
      onClick={onClick} 
      title={isCollapsed ? label : undefined}
      className={`w-full flex items-center ${
        isCollapsed ? "justify-center px-0 py-3" : "justify-start gap-3.5 px-3.5 py-3"
      } rounded-xl transition-all duration-200 group relative ${
        active 
          ? "bg-brand-green/20 text-brand-green glow-green font-bold" 
          : "text-white/40 hover:text-white/90 hover:bg-white/5"
      }`}
    >
      <div className="shrink-0 flex items-center justify-center">
        {icon}
      </div>
      {!isCollapsed && (
        <span className="text-sm font-semibold whitespace-nowrap overflow-hidden text-ellipsis">
          {label}
        </span>
      )}

      {isCollapsed && (
        <div className="hidden md:group-hover:block absolute left-full ml-3 px-2.5 py-1 bg-black/90 border border-white/10 rounded-md text-xs font-semibold text-white whitespace-nowrap z-50 pointer-events-none shadow-xl">
          {label}
        </div>
      )}
    </Link>
  );
}
