import React, { useState } from 'react';
import { Loader2, Languages, CheckCircle, RotateCcw, ChevronsDown, Pencil, X, Check } from 'lucide-react';
import type { Status, Segment } from '../types';

interface TranslationWorkspaceProps {
    status: Status;
    segments: Segment[];
    translatedSegments: Segment[];
    targetLang: string;
    setTargetLang: (val: string) => void;
    onDub: (voice: string) => void;
    onRetranslate: (id: string, mode: 'single' | 'all_after') => void;
    onUpdateTranslation?: (id: string, text: string) => void;
}

export const TranslationWorkspace: React.FC<TranslationWorkspaceProps> = ({
    status,
    segments,
    translatedSegments,
    targetLang,
    setTargetLang,
    onDub,
    onRetranslate,
    onUpdateTranslation
}) => {
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editText, setEditText] = useState("");
    const [selectedVoice, setSelectedVoice] = useState("default");

    const startEditing = (id: string, text: string) => {
        setEditingId(id);
        setEditText(text);
    };

    const saveEdit = () => {
        if (editingId && onUpdateTranslation) {
            onUpdateTranslation(editingId, editText);
        }
        setEditingId(null);
    };

    const cancelEdit = () => {
        setEditingId(null);
    };
    return (
        <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
            <div className="grid grid-cols-2 bg-slate-800 text-slate-200 text-xs font-bold uppercase tracking-widest">
                <div className="p-4 border-r border-slate-700">Original Transcription</div>
                <div className="p-4 flex items-center gap-2">
                    <Languages size={14} /> AI Translation
                </div>
            </div>

            <div className="h-[55vh] overflow-y-auto bg-white">
                {segments.length === 0 && (
                    <div className="h-full flex flex-col items-center justify-center text-slate-400">
                        <Loader2 className="animate-spin mb-2" />
                        <p className="text-sm">Waiting for AI to listen...</p>
                    </div>
                )}
                {segments.map((s) => {
                    const trans = translatedSegments.find((t) => t.id === s.id);
                    return (
                        <div key={s.id} className="grid grid-cols-2 border-b border-slate-100 items-stretch hover:bg-slate-50 transition-colors">
                            <div className="p-4 border-r border-slate-100">
                                <span className="text-[10px] text-blue-500 font-mono font-bold block mb-1">
                                    {Math.floor(s.start / 60)}:{(s.start % 60).toFixed(1).padStart(4, '0')}
                                </span>
                                <p className="text-sm leading-relaxed text-slate-700">{s.text}</p>
                            </div>
                            <div className="p-4">
                                {trans ? (
                                    <div className="group flex justify-between items-start animate-in fade-in slide-in-from-left-2 duration-500">
                                        {editingId === s.id ? (
                                            <div className="flex-1 mr-2">
                                                <textarea
                                                    value={editText}
                                                    onChange={(e) => setEditText(e.target.value)}
                                                    className="w-full text-sm p-2 border border-blue-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 min-h-[60px] resize-y"
                                                    autoFocus
                                                />
                                                <div className="flex justify-end gap-2 mt-2">
                                                    <button onClick={cancelEdit} className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 px-2 py-1 bg-slate-100 rounded transition-colors">
                                                        <X size={12} /> Cancel
                                                    </button>
                                                    <button onClick={saveEdit} className="flex items-center gap-1 text-xs bg-blue-500 text-white px-3 py-1 rounded hover:bg-blue-600 transition-colors shadow-sm">
                                                        <Check size={12} /> Save
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (
                                            <>
                                                <p
                                                    className="text-sm font-semibold text-slate-900 pr-2 flex-1 cursor-text hover:bg-slate-100 rounded p-1 -m-1 transition-colors"
                                                    onClick={() => startEditing(s.id, trans.text)}
                                                    title="Click to edit translation"
                                                >
                                                    {trans.text}
                                                </p>
                                                <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1 flex-shrink-0 ml-2">
                                                    <button
                                                        title="Edit translation"
                                                        onClick={() => startEditing(s.id, trans.text)}
                                                        className="text-slate-400 hover:text-green-500 p-1.5 rounded hover:bg-slate-100 transition-colors"
                                                    >
                                                        <Pencil size={14} />
                                                    </button>
                                                    <button
                                                        title="Retranslate this segment only"
                                                        onClick={() => onRetranslate(s.id, 'single')}
                                                        className="text-slate-400 hover:text-blue-500 p-1.5 rounded hover:bg-slate-100 transition-colors"
                                                    >
                                                        <RotateCcw size={14} />
                                                    </button>
                                                    <button
                                                        title="Retranslate from here onwards"
                                                        onClick={() => onRetranslate(s.id, 'all_after')}
                                                        className="text-slate-400 hover:text-orange-500 p-1.5 rounded hover:bg-slate-100 transition-colors"
                                                    >
                                                        <ChevronsDown size={14} />
                                                    </button>
                                                </div>
                                            </>
                                        )}
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        <div className="h-3 w-full bg-slate-100 animate-pulse rounded" />
                                        <div className="h-3 w-2/3 bg-slate-100 animate-pulse rounded" />
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            <div className="p-5 bg-slate-50 border-t flex justify-between items-center">
                <div className="flex items-center gap-4">
                    <select
                        value={targetLang}
                        onChange={(e) => setTargetLang(e.target.value)}
                        disabled={status !== 'idle' && status !== 'reviewing' && status !== 'translated'}
                        className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm font-medium focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                        <option value="zh">Translate to Chinese</option>
                        <option value="en">Translate to English</option>
                    </select>

                    <div className="flex gap-4 text-[11px] font-bold">
                        <span className="bg-blue-100 text-blue-700 px-2 py-1 rounded">TRANS: {segments.length}</span>
                        <span className="bg-green-100 text-green-700 px-2 py-1 rounded">DONE: {translatedSegments.length}</span>
                        {segments.length - translatedSegments.length > 0 && (
                            <span className="bg-orange-100 text-orange-700 px-2 py-1 rounded animate-pulse">
                                WAIT: {segments.length - translatedSegments.length}
                            </span>
                        )}
                    </div>
                </div>

                {status === 'translated' && (
                    <div className="flex items-center gap-3">
                        <select
                            value={selectedVoice}
                            onChange={(e) => setSelectedVoice(e.target.value)}
                            className="border border-slate-300 rounded-lg px-3 py-2 text-sm font-medium focus:ring-2 focus:ring-blue-500 outline-none bg-white"
                        >
                            <option value="default">Default Voice</option>
                            <option value="zh-CN-XiaoxiaoNeural">女声 (Xiaoxiao)</option>
                            <option value="zh-CN-YunxiNeural">男声 (Yunxi)</option>
                        </select>
                        <button
                            onClick={() => onDub(selectedVoice)}
                            className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-2.5 rounded-xl font-bold transition-all shadow-lg shadow-blue-200 flex items-center gap-2"
                        >
                            <CheckCircle size={18} /> Generate Dubbed Video
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};
