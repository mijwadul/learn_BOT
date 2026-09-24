import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import { ToastProvider } from "@/components/ui/Toast";
import { InstitutionalStatusBar } from "@/components/InstitutionalStatusBar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "BBMA Trading Dashboard | Institutional Quant Terminal",
  description: "Advanced AI Trading Bot & Institutional Quant Execution Terminal",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} flex h-screen overflow-hidden bg-brand-dark text-white`}>
        <ToastProvider>
          <Sidebar />
          <div className="flex-1 flex flex-col h-full overflow-hidden">
            <InstitutionalStatusBar />
            <main className="flex-1 overflow-y-auto pt-14 md:pt-0">
              {children}
            </main>
          </div>
        </ToastProvider>
      </body>
    </html>
  );
}
