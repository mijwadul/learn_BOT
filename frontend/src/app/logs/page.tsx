"use client";
import { useState, useEffect, useRef } from "react";
import { Terminal as TerminalIcon } from "lucide-react";

export default function LogsPage() {
  const [logs, setLogs] = useState<string[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let retryDelay = 2000;

    const connect = () => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

      const ws = new WebSocket("ws://localhost:8000/ws/logs");
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
        retryDelay = 2000;
        setLogs(prev => [...prev, `[SYSTEM] Connected to backend log stream.`]);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "log") {
            setLogs(prev => [...prev, msg.message].slice(-200));
          }
        } catch (err) {}
      };

      // FIX #10: Auto-reconnect saat koneksi terputus (misalnya backend restart)
      ws.onclose = () => {
        setWsConnected(false);
        wsRef.current = null;
        retryDelay = Math.min(retryDelay * 1.5, 30000);
        setLogs(prev => [...prev, `[SYSTEM] Connection lost. Reconnecting in ${Math.round(retryDelay / 1000)}s...`].slice(-200));
        reconnectTimeoutRef.current = setTimeout(connect, retryDelay);
      };

      ws.onerror = () => ws.close();
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, []);

  // Auto scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="mb-8 shrink-0 flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-black text-white tracking-widest flex items-center gap-3">
            <TerminalIcon className="text-brand-green" /> SYSTEM LOGS
          </h1>
          <p className="text-white/50 mt-2">Real-time terminal output from backend agents (wss://backend/ws/logs)</p>
        </div>
        <span className={`text-xs font-bold px-3 py-1 rounded-full flex items-center gap-1.5 mt-2 shrink-0 ${wsConnected ? 'bg-brand-green/20 text-brand-green' : 'bg-brand-red/20 text-brand-red animate-pulse'}`}>
          <span className="w-2 h-2 rounded-full bg-current" />
          {wsConnected ? 'CONNECTED' : 'RECONNECTING...'}
        </span>
      </div>

      <div 
        ref={scrollRef}
        className="flex-1 bg-black/80 rounded-xl border border-white/10 p-4 font-mono text-[11px] md:text-xs overflow-y-auto flex flex-col gap-1"
      >
        {logs.length === 0 ? (
           <span className="text-white/30 italic">Waiting for connection or python logs...</span>
        ) : (
           logs.map((log, i) => {
             const isWarning = log.includes('WARNING');
             const isError = log.includes('ERROR');
             let colorClass = "text-white/70";
             if (isWarning) colorClass = "text-yellow-400 font-bold";
             if (isError) colorClass = "text-brand-red font-bold";
             
             return (
               <div key={i} className={`${colorClass} hover:bg-white/5 px-2 py-0.5 rounded break-all`}>
                  {log}
               </div>
             )
           })
        )}
      </div>
    </div>
  );
}
