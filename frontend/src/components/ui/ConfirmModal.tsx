"use client";

import React from "react";
import { AlertOctagon, AlertTriangle, Info, X } from "lucide-react";

export interface ConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: string;
  description: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "danger" | "warning" | "info";
  isLoading?: boolean;
}

export function ConfirmModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = "Konfirmasi",
  cancelText = "Batal",
  variant = "danger",
  isLoading = false,
}: ConfirmModalProps) {
  if (!isOpen) return null;

  let icon = <AlertOctagon className="w-8 h-8 text-brand-red" />;
  let confirmBtnClass = "bg-brand-red hover:bg-brand-red/80 text-white shadow-lg shadow-brand-red/30";
  let iconBg = "bg-brand-red/10 border-brand-red/20";

  if (variant === "warning") {
    icon = <AlertTriangle className="w-8 h-8 text-amber-400" />;
    confirmBtnClass = "bg-amber-500 hover:bg-amber-600 text-black font-bold shadow-lg shadow-amber-500/30";
    iconBg = "bg-amber-500/10 border-amber-500/20";
  } else if (variant === "info") {
    icon = <Info className="w-8 h-8 text-cyan-400" />;
    confirmBtnClass = "bg-cyan-500 hover:bg-cyan-600 text-black font-bold shadow-lg shadow-cyan-500/30";
    iconBg = "bg-cyan-500/10 border-cyan-500/20";
  }

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-4">
      {/* Glassmorphism Backdrop */}
      <div 
        className="fixed inset-0 bg-black/80 backdrop-blur-md transition-opacity animate-in fade-in"
        onClick={isLoading ? undefined : onClose}
      />

      {/* Modal Dialog Content */}
      <div className="relative w-full max-w-lg bg-[#0e1614] border border-white/10 rounded-2xl p-6 shadow-2xl z-10 animate-in zoom-in-95 duration-200">
        <div className="flex items-start gap-4">
          <div className={`p-3 rounded-xl border ${iconBg} shrink-0`}>
            {icon}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-bold text-white tracking-wide">{title}</h3>
            <p className="mt-2 text-sm text-white/70 leading-relaxed">{description}</p>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="text-white/40 hover:text-white p-1 rounded-lg transition-colors shrink-0 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="mt-6 flex items-center justify-end gap-3 pt-4 border-t border-white/10">
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2.5 rounded-xl border border-white/10 text-white/70 hover:text-white hover:bg-white/5 font-semibold text-sm transition-colors disabled:opacity-50"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-5 py-2.5 rounded-xl font-bold text-sm transition-all flex items-center gap-2 disabled:opacity-50 ${confirmBtnClass}`}
          >
            {isLoading && (
              <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
            )}
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
