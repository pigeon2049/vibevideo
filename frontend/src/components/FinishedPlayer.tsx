import React from 'react';

interface FinishedPlayerProps {
    videoUrl: string;
    onBack: () => void;
}

export const FinishedPlayer: React.FC<FinishedPlayerProps> = ({ videoUrl, onBack }) => {
    return (
        <div className="space-y-6 animate-in zoom-in-95 duration-500">
            <div className="bg-black rounded-3xl overflow-hidden shadow-2xl ring-8 ring-white">
                <video
                    controls
                    autoPlay
                    src={videoUrl}
                    className="w-full aspect-video"
                />
            </div>
            <div className="flex justify-center gap-4 mt-6">
                <button
                    onClick={() => {
                        localStorage.removeItem('vibe_project_id');
                        window.location.reload();
                    }}
                    className="bg-slate-800 hover:bg-slate-900 text-white px-10 py-4 rounded-2xl font-bold transition-all shadow-md"
                >
                    Start New Project
                </button>
                <button
                    onClick={onBack}
                    className="bg-slate-200 hover:bg-slate-300 text-slate-800 px-10 py-4 rounded-2xl font-bold transition-all shadow-md"
                >
                    Back to Last Step
                </button>
            </div>
        </div>
    );
};
