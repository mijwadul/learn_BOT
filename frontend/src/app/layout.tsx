import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "BBMA Trading Dashboard",
  description: "Advanced AI Trading Bot Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} flex h-screen overflow-hidden bg-brand-dark`}>
        <Sidebar />
        <main className="flex-1 overflow-y-auto pt-16 md:pt-0">
          {children}
        </main>
      </body>
    </html>
  );
}
