"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { CheckCircle2, AlertTriangle, AlertCircle, Info, X } from "lucide-react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastMessage {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

interface ToastContextType {
  toast: {
    success: (message: string, title?: string, duration?: number) => void;
    error: (message: string, title?: string, duration?: number) => void;
    warning: (message: string, title?: string, duration?: number) => void;
    info: (message: string, title?: string, duration?: number) => void;
  };
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((type: ToastType, message: string, title?: string, duration = 4000) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, title, message, duration }]);

    if (duration > 0) {
      setTimeout(() => {
        removeToast(id);
      }, duration);
    }
  }, [removeToast]);

  const toast = {
    success: (msg: string, title?: string, dur?: number) => addToast("success", msg, title || "Berhasil", dur),
    error: (msg: string, title?: string, dur?: number) => addToast("error", msg, title || "Gagal", dur),
    warning: (msg: string, title?: string, dur?: number) => addToast("warning", msg, title || "Peringatan", dur),
    info: (msg: string, title?: string, dur?: number) => addToast("info", msg, title || "Informasi", dur),
  };

  return (
    <ToastContext.Provider value={{ toast, removeToast }}>
      {children}
      {/* Toast Notification Container */}
      <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2.5 max-w-md w-full pointer-events-none px-4 sm:px-0">
        {toasts.map((t) => {
          let borderCol = "border-brand-green/40 bg-[#0d1f18]/95 text-brand-green";
          let icon = <CheckCircle2 className="w-5 h-5 text-brand-green shrink-0 mt-0.5" />;

          if (t.type === "error") {
            borderCol = "border-brand-red/50 bg-[#241014]/95 text-brand-red";
            icon = <AlertCircle className="w-5 h-5 text-brand-red shrink-0 mt-0.5" />;
          } else if (t.type === "warning") {
            borderCol = "border-amber-500/40 bg-[#211a0d]/95 text-amber-400";
            icon = <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />;
          } else if (t.type === "info") {
            borderCol = "border-cyan-500/40 bg-[#0a1b24]/95 text-cyan-400";
            icon = <Info className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />;
          }

          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl border backdrop-blur-md shadow-2xl transition-all duration-300 animate-in slide-in-from-bottom-3 ${borderCol}`}
            >
              {icon}
              <div className="flex-1 min-w-0">
                {t.title && <h4 className="text-xs font-bold uppercase tracking-wider mb-0.5">{t.title}</h4>}
                <p className="text-sm font-medium text-white/90 leading-snug break-words">{t.message}</p>
              </div>
              <button
                onClick={() => removeToast(t.id)}
                className="text-white/40 hover:text-white p-1 rounded-md transition-colors shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context.toast;
}
