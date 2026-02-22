import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import type { Status, Segment } from '../types';

const API_BASE_URL = "http://localhost:8000/api/v1";

export function useTranslationPipeline() {
    const [status, setStatus] = useState<Status>('idle');
    const [projectId, setProjectId] = useState<string | null>(null);
    const [segments, setSegments] = useState<Segment[]>([]);
    const [translatedSegments, setTranslatedSegments] = useState<Segment[]>([]);
    const [targetLang, setTargetLang] = useState('zh');
    const [finalVideo, setFinalVideo] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [dubbingProgress, setDubbingProgress] = useState<{ step: string, current?: number, total?: number } | null>(null);
    const [dubbingParagraphs, setDubbingParagraphs] = useState<any[]>([]);

    const isProcessingRef = useRef<boolean>(false);

    const restoreProject = useCallback(async (id: string) => {
        try {
            const res = await axios.get(`${API_BASE_URL}/projects/${id}`);
            const data = res.data;

            setProjectId(data.id);
            setStatus(data.status === 'dubbing' ? 'translated' : data.status);

            if (data.status === 'finished' && data.final_video_url) {
                setFinalVideo(data.final_video_url);
            }

            const parsedLang = data.target_language === 'Chinese' ? 'zh' : (data.target_language === 'English' ? 'en' : data.target_language);
            if (parsedLang) setTargetLang(parsedLang);

            setSegments(data.segments.map((s: any) => ({
                id: s.id, start: s.start, end: s.end, text: s.text
            })));
            setTranslatedSegments(data.segments
                .filter((s: any) => s.text_translated)
                .map((s: any) => ({
                    id: s.id, start: s.start, end: s.end, text: s.text_translated
                })));

        } catch (err: any) {
            console.error("Failed to restore project:", err);
            setError("恢复项目失败");
        }
    }, []);

    const handleVideoSelected = (data: any) => {
        setProjectId(data.project_id);
        localStorage.setItem('vibe_project_id', data.project_id);
        setSegments([]);
        setTranslatedSegments([]);
        setStatus('transcribing');
        setError(null);

        const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/transcribe`);
        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === "segment") setSegments(p => [...p, msg.data]);
            if (msg.type === "done") restoreProject(data.project_id);
            if (msg.type === "error") {
                setError(msg.message);
                setStatus('idle');
            }
        };
        ws.onopen = () => ws.send(JSON.stringify({ project_id: data.project_id }));
    };

    const processTranslationQueue = useCallback(async () => {
        if (isProcessingRef.current || !projectId) return;
        const pendingCount = segments.length - translatedSegments.length;
        if (pendingCount === 0) return;

        isProcessingRef.current = true;
        try {
            const res = await fetch(`${API_BASE_URL}/translate-stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: projectId,
                    target_language: targetLang === 'zh' ? 'Chinese' : 'English',
                    context: translatedSegments.slice(-5).map(s => s.text)
                })
            });

            const reader = res.body?.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            if (reader) {
                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || "";
                    for (const line of lines) {
                        if (!line.trim()) continue;
                        const chunk: Segment[] = JSON.parse(line);
                        setTranslatedSegments(prev => {
                            const merged = [...prev];
                            chunk.forEach(ns => {
                                const idx = merged.findIndex(s => s.id === ns.id);
                                if (idx >= 0) merged[idx] = ns; else merged.push(ns);
                            });
                            return merged.sort((a, b) => a.start - b.start);
                        });
                    }
                }
            }
        } catch (e) {
            console.error("Translation error:", e);
        } finally {
            isProcessingRef.current = false;
        }
    }, [projectId, segments.length, translatedSegments, targetLang]);

    useEffect(() => {
        if (['reviewing', 'translating'].includes(status)) {
            processTranslationQueue();
        }
        if (segments.length > 0 && segments.length === translatedSegments.length && status === 'translating') {
            setStatus('translated');
        }
    }, [segments.length, translatedSegments.length, status, processTranslationQueue]);

    const handleDub = async (voice: string = 'default') => {
        setStatus('dubbing');
        try {
            const res = await fetch(`${API_BASE_URL}/dub`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: projectId,
                    voice: voice
                })
            });
            const reader = res.body?.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            if (reader) {
                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || "";
                    for (const line of lines) {
                        if (!line.trim()) continue;
                        const msg = JSON.parse(line);
                        if (msg.step === "done") {
                            setFinalVideo(msg.url);
                            setStatus('finished');
                        } else if (msg.step === "tts") {
                            setDubbingProgress(msg);
                            if (msg.paragraphs) {
                                setDubbingParagraphs(msg.paragraphs);
                            } else if (msg.paragraph) {
                                setDubbingParagraphs(prev => prev.map(p =>
                                    p.id === msg.paragraph.id ? msg.paragraph : p
                                ));
                            }
                        } else {
                            setDubbingProgress(msg);
                        }
                    }
                }
            }
        } catch (e: any) {
            setError(e.message);
            setStatus('translated');
        }
    };

    const handleRetranslate = async (segmentId: string, mode: 'single' | 'all_after' = 'single') => {
        if (!projectId) return;
        try {
            await axios.post(`${API_BASE_URL}/projects/${projectId}/segment/${segmentId}/reset?mode=${mode}`);
            if (mode === 'single') {
                setTranslatedSegments(prev => prev.filter(t => t.id !== segmentId));
            } else {
                restoreProject(projectId);
            }
            if (status === 'translated') setStatus('reviewing');
        } catch (err) {
            console.error("Failed to reset segment translation", err);
        }
    };

    const handleUpdateTranslation = async (segmentId: string, newText: string) => {
        if (!projectId) return;
        try {
            await axios.put(`${API_BASE_URL}/projects/${projectId}/segment/${segmentId}/translation`, {
                text_translated: newText
            });
            setTranslatedSegments(prev =>
                prev.map(t => t.id === segmentId ? { ...t, text: newText } : t)
            );
        } catch (err) {
            console.error("Failed to update segment translation", err);
        }
    };

    return {
        status, setStatus,
        projectId,
        segments,
        translatedSegments,
        targetLang, setTargetLang,
        finalVideo,
        error,
        dubbingProgress,
        dubbingParagraphs,
        handleVideoSelected,
        handleDub,
        handleRetranslate,
        handleUpdateTranslation,
        restoreProject
    };
}
