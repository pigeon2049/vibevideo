import { Video } from 'lucide-react';
import { SystemStatus } from './SystemStatus';

interface HeaderProps {
    status: string;
}

export const Header: React.FC<HeaderProps> = ({ status }) => {
    return (
        <header className="flex w-full max-w-5xl items-center justify-between mb-8">
            <div className="flex items-center gap-2">
                <Video className="text-blue-600" size={32} />
                <h1 className="text-3xl font-black tracking-tight text-slate-800">Vibe Video</h1>
            </div>
            <div className="flex items-center gap-4">
                <SystemStatus />
                {status !== 'idle' && (
                    <button
                        onClick={() => {
                            localStorage.removeItem('vibe_project_id');
                            window.location.reload();
                        }}
                        className="text-sm font-semibold text-slate-500 hover:text-slate-800 transition-colors"
                    >
                        Start New Project
                    </button>
                )}
            </div>
        </header>
    );
};
