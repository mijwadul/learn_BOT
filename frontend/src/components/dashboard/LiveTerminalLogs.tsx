"use client";

import React from "react";

interface LiveTerminalLogsProps {
  logs: string[];
  logsScrollRef: React.RefObject<HTMLDivElement>;
}

export const LiveTerminalLogs: React.FC<LiveTerminalLogsProps> = ({ logs, logsScrollRef }) => {
  return (
    <div
      ref={logsScrollRef}
      className="w-full h-full p-4 font-mono text-xs overflow-y-auto custom-scrollbar bg-black/80 flex flex-col gap-1.5"
    >
      {logs.length === 0 ? (
        <span className="text-white/30 italic">Menghubungkan ke streaming log AI Autonomous Engine...</span>
      ) : (
        logs.map((log, i) => {
          const isWarning = log.includes("WARNING");
          const isError = log.includes("ERROR");
          const isSignal = log.includes("[SIGNAL]");
          const isSekring = log.includes("[SEKRING]");
          let colorClass = "text-white/70";
          if (isSignal) colorClass = "text-emerald-300 font-bold bg-emerald-950/20";
          else if (isSekring) colorClass = "text-amber-300 font-bold bg-amber-950/20";
          else if (isWarning) colorClass = "text-yellow-400 font-bold";
          else if (isError) colorClass = "text-rose-400 font-bold";
          return (
            <div key={i} className={`${colorClass} hover:bg-white/5 px-2 py-0.5 rounded break-all`}>
              {log}
            </div>
          );
        })
      )}
    </div>
  );
};
