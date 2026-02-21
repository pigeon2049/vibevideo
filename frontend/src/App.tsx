import { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { VideoInput } from './components/VideoInput'
import { Header } from './components/Header'
import { DubbingStep } from './components/DubbingStep'
import { FinishedPlayer } from './components/FinishedPlayer'
import { TranslationWorkspace } from './components/TranslationWorkspace'
import type { Status, Segment } from './types'

const API_URL = "http://localhost:8000"

function App() {
  const [status, setStatus] = useState<Status>('idle')
  const [projectId, setProjectId] = useState<string | null>(null)
  const [segments, setSegments] = useState<Segment[]>([])
  const [translatedSegments, setTranslatedSegments] = useState<Segment[]>([])
  const [targetLang, setTargetLang] = useState('zh')
  const [finalVideo, setFinalVideo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 队列控制 Refs
  const isProcessingRef = useRef<boolean>(false)

  // ==================================================
  // 核心：翻译队列逻辑
  // ==================================================

  useEffect(() => {
    // 页面加载时恢复上次的 Project
    const savedProjectId = localStorage.getItem('vibe_project_id');
    if (savedProjectId && status === 'idle') {
      restoreProject(savedProjectId);
    }
  }, []);

  const restoreProject = async (id: string) => {
    try {
      const res = await axios.get(`${API_URL}/project/${id}`);
      const data = res.data;

      setProjectId(data.id);
      setStatus(data.status);
      setTargetLang(data.target_language);

      // 恢复片段
      const allSegments = data.segments.map((s: any) => ({
        id: s.id, start: s.start, end: s.end, text: s.text
      }));
      const translated = data.segments
        .filter((s: any) => s.text_translated)
        .map((s: any) => ({
          id: s.id, start: s.start, end: s.end, text: s.text_translated
        }));

      setSegments(allSegments);
      setTranslatedSegments(translated);

    } catch (err) {
      console.error("Failed to restore project:", err);
      // 如果报错说明项目不存在或过期，清除 localStorage
      localStorage.removeItem('vibe_project_id');
    }
  };

  useEffect(() => {
    const pendingCount = segments.length - translatedSegments.length;

    if (pendingCount > 0 && ['reviewing', 'translating'].includes(status) && !isProcessingRef.current) {
      processQueue();
    } else if (pendingCount === 0 && segments.length > 0 && ['reviewing', 'translating'].includes(status)) {
      setStatus('translated');
    }
  }, [segments, translatedSegments, status]);

  const processQueue = async () => {
    const pendingCount = segments.length - translatedSegments.length;
    if (isProcessingRef.current || pendingCount === 0) return;

    isProcessingRef.current = true;
    const context = translatedSegments.slice(-5).map(s => s.text);

    try {
      const res = await fetch(`${API_URL}/translate-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          target_language: targetLang === 'zh' ? 'Chinese' : 'English',
          context: context
        })
      });

      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      if (reader) {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          // 处理最后一行可能不完整的情况
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const chunk: Segment[] = JSON.parse(line);
              setTranslatedSegments(prev => {
                const merged = [...prev];
                chunk.forEach(ns => {
                  const idx = merged.findIndex(s => s.id === ns.id);
                  if (idx >= 0) {
                    merged[idx] = ns;
                  } else {
                    merged.push(ns);
                  }
                });
                return [...merged].sort((a, b) => a.start - b.start);
              });
            } catch (e) {
              console.error("JSON parse error in stream:", e, "Line:", line);
            }
          }
        }
      }

    } catch (e: any) {
      console.error("❌ Queue process error:", e);
      // 报错后等待 2 秒自动重试，防止死循环
      await new Promise(resolve => setTimeout(resolve, 2000));
    } finally {
      isProcessingRef.current = false;
      // 退出 processing 后，如果有依赖项更新，`useEffect` 会重新调用 processQueue()
    }
  };

  // ==================================================
  // 交互处理
  // ==================================================

  const handleRetranslate = async (segmentId: string, mode: 'single' | 'all_after' = 'single') => {
    if (!projectId) return;
    try {
      await axios.post(`${API_URL}/project/${projectId}/segment/${segmentId}/reset?mode=${mode}`);
      // Update local state to remove the translated segment, which will trigger the queue processor
      if (mode === 'single') {
        setTranslatedSegments(prev => prev.filter(t => t.id !== segmentId));
      } else {
        const res = await axios.get(`${API_URL}/project/${projectId}`);
        const data = res.data;
        setStatus(data.status);
        const translated = data.segments
          .filter((s: any) => s.text_translated)
          .map((s: any) => ({
            id: s.id, start: s.start, end: s.end, text: s.text_translated
          }));
        setTranslatedSegments(translated);
      }

      if (status === 'translated') {
        setStatus('reviewing');
      }
    } catch (err) {
      console.error("Failed to reset segment translation", err);
    }
  };

  const handleVideoSelected = (data: any) => {
    setProjectId(data.project_id);
    localStorage.setItem('vibe_project_id', data.project_id);

    setSegments([]);
    setTranslatedSegments([]);
    isProcessingRef.current = false;
    setStatus('transcribing');
    setError(null);

    const ws = new WebSocket(`${API_URL.replace('http', 'ws')}/ws/transcribe`);
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "segment") setSegments(p => [...p, msg.data]);
      if (msg.type === "done") setStatus('reviewing');
      if (msg.type === "error") {
        setError(msg.message);
        setStatus('idle');
      }
    };
    ws.onopen = () => ws.send(JSON.stringify({
      video_path: data.path,
      project_id: data.project_id
    }));
    ws.onerror = () => setError("WebSocket connection failed.");
  };

  const handleDub = async () => {
    setStatus('dubbing');
    try {
      const res = await axios.post(`${API_URL}/dub`, {
        project_id: projectId,
        voice: targetLang === 'zh' ? 'zh-CN-XiaoxiaoNeural' : 'en-US-AriaNeural'
      });
      setFinalVideo(res.data.url);
      setStatus('finished');
    } catch (e: any) {
      setError(e.response?.data?.detail || e.message);
      setStatus('translated');
    }
  };

  // ==================================================
  // 渲染逻辑
  // ==================================================

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center py-8 px-4 font-sans text-slate-900">
      <Header status={status} />

      {error && (
        <div className="w-full max-w-5xl p-4 mb-4 bg-red-50 border border-red-200 text-red-700 rounded-xl flex items-center gap-2">
          <span className="font-bold">Error:</span> {error}
        </div>
      )}

      <div className="w-full max-w-5xl">
        {status === 'idle' && <VideoInput onVideoSelected={handleVideoSelected} />}

        {['transcribing', 'reviewing', 'translating', 'translated'].includes(status) && (
          <TranslationWorkspace
            status={status}
            segments={segments}
            translatedSegments={translatedSegments}
            targetLang={targetLang}
            setTargetLang={setTargetLang}
            onDub={handleDub}
            onRetranslate={handleRetranslate}
          />
        )}

        {status === 'dubbing' && <DubbingStep />}

        {status === 'finished' && finalVideo && (
          <FinishedPlayer videoUrl={`${API_URL}${finalVideo}`} />
        )}
      </div>
    </div>
  )
}

export default App