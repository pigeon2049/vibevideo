import React, { useState, useEffect, useRef } from 'react';
import { Cpu, Activity, Database } from 'lucide-react';

interface SystemStats {
    cpu: {
        percent: number;
        cores: number;
    };
    memory: {
        percent: number;
        used: number;
        total: number;
    };
    gpu?: {
        id: number;
        name: string;
        load: number;
        memory_percent: number;
        memory_total: number;
        memory_used: number;
        memory_free: number;
    }[] | null;
}

export const SystemStatus: React.FC = () => {
    const [stats, setStats] = useState<SystemStats | null>(null);
    const [connected, setConnected] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        const connectWs = () => {
            const ws = new WebSocket('ws://localhost:8000/api/v1/system/ws/status');
            wsRef.current = ws;

            ws.onopen = () => {
                setConnected(true);
                console.log('System Status WS Connected');
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                setStats(data);
            };

            ws.onerror = (error) => {
                console.error('System Status WS Error:', error);
                setConnected(false);
            };

            ws.onclose = () => {
                setConnected(false);
                console.log('System Status WS Disconnected, retrying in 5s...');
                setTimeout(connectWs, 5000);
            };
        };

        connectWs();

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, []);

    if (!stats) return null;

    return (
        <div className="flex items-center gap-6 px-4 py-2 bg-slate-50 rounded-xl border border-slate-100 shadow-sm backdrop-blur-sm bg-opacity-80">
            {/* CPU */}
            <div className="flex items-center gap-2" title={`CPU Usage: ${stats.cpu.percent}%`}>
                <Cpu size={14} className="text-blue-500" />
                <div className="flex flex-col">
                    <span className="text-[10px] uppercase font-bold text-slate-400 leading-tight">CPU</span>
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-slate-700">{stats.cpu.percent.toFixed(1)}%</span>
                        <div className="w-12 h-1 bg-slate-200 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-blue-500 transition-all duration-500 ease-out"
                                style={{ width: `${stats.cpu.percent}%` }}
                            />
                        </div>
                    </div>
                </div>
            </div>

            {/* RAM */}
            <div className="flex items-center gap-2" title={`RAM Usage: ${stats.memory.percent}%`}>
                <Activity size={14} className="text-emerald-500" />
                <div className="flex flex-col">
                    <span className="text-[10px] uppercase font-bold text-slate-400 leading-tight">RAM</span>
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-mono font-bold text-slate-700">{stats.memory.percent.toFixed(0)}%</span>
                        <div className="w-12 h-1 bg-slate-200 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-emerald-500 transition-all duration-500 ease-out"
                                style={{ width: `${stats.memory.percent}%` }}
                            />
                        </div>
                    </div>
                </div>
            </div>

            {/* GPU */}
            {stats.gpu && stats.gpu.length > 0 && stats.gpu.map(gpu => (
                <div key={gpu.id} className="flex items-center gap-2" title={`${gpu.name}: ${gpu.load}% load, ${gpu.memory_percent}% VRAM`}>
                    <Database size={14} className="text-orange-500" />
                    <div className="flex flex-col">
                        <span className="text-[10px] uppercase font-bold text-slate-400 leading-tight">GPU</span>
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-mono font-bold text-slate-700">{gpu.load}%</span>
                            <div className="w-12 h-1 bg-slate-200 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-orange-500 transition-all duration-500 ease-out"
                                    style={{ width: `${gpu.load}%` }}
                                />
                            </div>
                        </div>
                    </div>
                </div>
            ))}

            {!connected && (
                <div className="w-2 h-2 rounded-full bg-red-400 animate-pulse" title="Disconnected" />
            )}
        </div>
    );
};
