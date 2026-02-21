import React from 'react';
import { Loader2, Video } from 'lucide-react';

export const DubbingStep: React.FC = () => {
    return (
        <div className="text-center py-20 bg-white rounded-3xl shadow-2xl border border-slate-100">
            <div className="relative inline-block mb-6">
                <Loader2 className="animate-spin text-blue-600" size={64} />
                <div className="absolute inset-0 flex items-center justify-center">
                    <Video size={20} className="text-blue-400" />
                </div>
            </div>
            <h2 className="text-xl font-bold text-slate-800 mb-2">Creating Magic...</h2>
            <p className="text-slate-500 max-w-xs mx-auto text-sm">
                We're separating audio layers and synthesizing high-quality AI voice. This may take a minute.
            </p>
        </div>
    );
};
