import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Trash2, ChevronDown, ChevronUp } from 'lucide-react';

export const LogTerminal: React.FC = () => {
    const [logs, setLogs] = useState<string[]>([]);
    const [isConnected, setIsConnected] = useState(false);
    const [isExpanded, setIsExpanded] = useState(true);
    const terminalRef = useRef<HTMLDivElement>(null);
    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        const connectWs = () => {
            const ws = new WebSocket('ws://localhost:8000/api/v1/system/ws/logs');
            wsRef.current = ws;

            ws.onopen = () => {
                setIsConnected(true);
                console.log('Log WS Connected');
            };

            ws.onmessage = (event) => {
                setLogs(prev => [...prev.slice(-1000), event.data]);
            };

            ws.onerror = (error) => {
                console.error('Log WS Error:', error);
                setIsConnected(false);
            };

            ws.onclose = () => {
                setIsConnected(false);
                console.log('Log WS Disconnected, retrying in 5s...');
                setTimeout(connectWs, 5000);
            };
        };

        connectWs();

        return () => {
            if (wsRef.current) wsRef.current.close();
        };
    }, []);

    useEffect(() => {
        if (terminalRef.current && isExpanded) {
            terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
        }
    }, [logs, isExpanded]);

    const clearLogs = () => setLogs([]);

    return (
        <div className={`fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-5xl transition-all duration-300 ease-in-out z-50 ${isExpanded ? 'h-64' : 'h-10'}`}>
            <div className="bg-slate-900 rounded-t-xl border-x border-t border-slate-700 shadow-2xl overflow-hidden flex flex-col h-full">
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-2 bg-slate-800 border-b border-slate-700 cursor-pointer select-none"
                    onClick={() => setIsExpanded(!isExpanded)}>
                    <div className="flex items-center gap-2">
                        <Terminal size={14} className="text-emerald-400" />
                        <span className="text-xs font-bold text-slate-300 uppercase tracking-widest">System Logs</span>
                        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-red-500'} animate-pulse`} />
                    </div>
                    <div className="flex items-center gap-4">
                        <button
                            onClick={(e) => { e.stopPropagation(); clearLogs(); }}
                            className="p-1 hover:bg-slate-700 rounded text-slate-400 hover:text-white transition-colors"
                            title="Clear Logs"
                        >
                            <Trash2 size={14} />
                        </button>
                        {isExpanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronUp size={16} className="text-slate-400" />}
                    </div>
                </div>

                {/* Log Content */}
                {isExpanded && (
                    <div
                        ref={terminalRef}
                        className="flex-1 p-4 font-mono text-[11px] overflow-y-auto bg-slate-950 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent"
                    >
                        {logs.length === 0 ? (
                            <div className="text-slate-600 italic">Waiting for logs...</div>
                        ) : (
                            logs.map((log, i) => {
                                let textColor = "text-slate-300";
                                if (log.includes("[ERROR]")) textColor = "text-red-400";
                                if (log.includes("[WARNING]")) textColor = "text-amber-400";
                                if (log.includes("[INFO]")) textColor = "text-emerald-400";

                                return (
                                    <div key={i} className={`mb-1 break-all leading-relaxed ${textColor}`}>
                                        <span className="opacity-50 inline-block mr-2 select-none">{i + 1}</span>
                                        {log}
                                    </div>
                                );
                            })
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};
