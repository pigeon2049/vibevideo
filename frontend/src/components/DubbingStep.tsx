import React from 'react';
import { Loader2, Video, Mic, Scissors, Combine } from 'lucide-react';

export interface DubbingProgress {
    step: string;
    current?: number;
    total?: number;
}

export interface DubbingParagraph {
    id: string;
    text: string;
    start: number;
    audio_url?: string;
}

interface DubbingStepProps {
    progress?: DubbingProgress | null;
    paragraphs?: DubbingParagraph[];
    baseUrl?: string;
}

export const DubbingStep: React.FC<DubbingStepProps> = ({ progress, paragraphs = [], baseUrl = "" }) => {
    const getStepDetails = () => {
        if (!progress) return { title: "Starting...", icon: <Loader2 size={24} className="animate-spin text-blue-600" /> };
        switch (progress.step) {
            case 'tts':
                return {
                    title: `Synthesizing Audio (${progress.current}/${progress.total})`,
                    icon: <Mic size={24} className="text-blue-500 animate-pulse" />,
                    perc: progress.total ? Math.round((progress.current || 0) / progress.total * 100) : 0
                };
            case 'isolate':
                return { title: "Isolating Audio Layer...", icon: <Scissors size={24} className="text-purple-500" /> };
            case 'separate':
                return { title: "Separating Vocals...", icon: <Scissors size={24} className="text-purple-500" /> };
            case 'merge':
                return { title: "Merging Final Video...", icon: <Combine size={24} className="text-orange-500" /> };
            default:
                return { title: "Finishing up...", icon: <Video size={24} className="text-green-500" /> };
        }
    };

    const details = getStepDetails();

    return (
        <div className="text-center py-20 bg-white rounded-3xl shadow-2xl border border-slate-100 transition-all duration-300">
            <div className="relative inline-block mb-6 h-20 w-20 flex items-center justify-center bg-slate-50 rounded-full shadow-inner">
                {progress?.step === 'tts' && (
                    <div className="absolute inset-0 rounded-full border-4 border-blue-50 border-t-blue-500 animate-spin" />
                )}
                {details.icon}
            </div>
            <h2 className="text-xl font-bold text-slate-800 mb-2">{details.title}</h2>

            {progress?.step === 'tts' && progress.total !== undefined ? (
                <div className="w-64 mx-auto mt-6">
                    <div className="bg-slate-100 h-2 rounded-full overflow-hidden shadow-inner">
                        <div
                            className="bg-blue-500 h-full transition-all duration-300 ease-out"
                            style={{ width: `${details.perc}%` }}
                        />
                    </div>
                </div>
            ) : (
                <p className="text-slate-500 max-w-xs mx-auto text-sm mt-4">
                    Processing high-quality AI voice and audio layers...
                </p>
            )}

            {paragraphs.length > 0 && progress?.step === 'tts' && (
                <div className="mt-10 mx-auto max-w-3xl text-left bg-slate-50 rounded-2xl p-6 shadow-inner border border-slate-200 h-[60vh] overflow-y-auto">
                    <h3 className="text-lg font-semibold text-slate-700 mb-4 sticky top-0 bg-slate-50 pb-2 border-b border-slate-200 z-10">Real-time Audio Preview</h3>
                    <div className="space-y-4">
                        {paragraphs.map(p => (
                            <div key={p.id} className={`p-4 rounded-xl border transition-all duration-500 ${p.audio_url ? 'bg-white border-green-200 shadow-sm' : 'bg-slate-100/50 border-slate-200 text-slate-400'}`}>
                                <p className="mb-3 text-[15px] leading-relaxed select-text">{p.text}</p>
                                {p.audio_url ? (
                                    <audio controls src={`${baseUrl}${p.audio_url}`} className="h-10 w-full rounded-full" />
                                ) : (
                                    <div className="flex items-center gap-2 text-sm text-slate-400">
                                        <Loader2 size={14} className="animate-spin" />
                                        Synthesizing...
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};
