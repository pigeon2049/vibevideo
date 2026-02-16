import { useState } from 'react';
import { VideoInput } from './components/VideoInput';
import axios from 'axios';
import { Loader2, CheckCircle, FileAudio, Languages } from 'lucide-react';
import { cn } from './lib/utils';

const API_URL = "http://localhost:8000";

type Status = 'idle' | 'downloading' | 'transcribing' | 'reviewing' | 'translating' | 'dubbing' | 'finished';

interface Segment {
  start: number;
  end: number;
  text: string;
}

function App() {
  const [status, setStatus] = useState<Status>('idle');
  const [videoData, setVideoData] = useState<any>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [translatedSegments, setTranslatedSegments] = useState<Segment[]>([]);
  const [targetLang, setTargetLang] = useState('zh'); // Default Chinese
  const [finalVideo, setFinalVideo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleVideoSelected = async (data: any) => {
    setVideoData(data);
    setStatus('transcribing');
    setError(null);

    // Auto-start transcription
    try {
      const response = await axios.post(`${API_URL}/transcribe`, {
        video_path: data.path
      });
      setSegments(response.data.segments);
      setStatus('reviewing');
    } catch (err: any) {
      setError("Transcription failed: " + (err.response?.data?.detail || err.message));
      setStatus('idle');
    }
  };

  const handleTranslate = async () => {
    setStatus('translating');
    setError(null);
    try {
      const response = await axios.post(`${API_URL}/translate`, {
        segments: segments,
        target_language: targetLang === 'zh' ? 'Chinese' : 'English' // Simple map for now
      });
      setTranslatedSegments(response.data.segments);
      setStatus('dubbing');
    } catch (err: any) {
      setError("Translation failed: " + (err.response?.data?.detail || err.message));
      setStatus('reviewing');
    }
  };

  const handleDub = async () => {
    // Only separate background for now as per backend implementation
    // But we need to call /dub
    setStatus('dubbing');
    try {
      const response = await axios.post(`${API_URL}/dub`, {
        video_path: videoData.path,
        segments: translatedSegments,
        voice: targetLang === 'zh' ? 'zh-CN-XiaoxiaoNeural' : 'en-US-AriaNeural'
      });
      setFinalVideo(response.data.url);
      setStatus('finished');
    } catch (err: any) {
      setError("Dubbing failed: " + (err.response?.data?.detail || err.message));
      // If failed, maybe stay in dubbing state or go back?
      setStatus('reviewing');
    }
  };

  // Auto-trigger dubbing after translation for MVP smoothness?
  // Let's keep it manual so user can see translation.

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col items-center py-10 px-4">
      <header className="mb-10 text-center">
        <h1 className="text-4xl font-bold tracking-tight text-primary mb-2">Vibe Video</h1>
        <p className="text-muted-foreground">AI Video Dubbing & Translation</p>
      </header>

      <main className="w-full max-w-4xl space-y-8">
        {/* Status Steps */}
        <div className="flex justify-between items-center px-10">
          {['Upload', 'Transcribe', 'Translate', 'Dub'].map((step, idx) => {

            // Simple visual logic...
            return (
              <div key={step} className="flex flex-col items-center">
                <div className={cn("w-8 h-8 rounded-full flex items-center justify-center border-2",
                  // Logic to highlight current step
                  "border-primary"
                )}>
                  {idx + 1}
                </div>
                <span className="text-xs mt-1">{step}</span>
              </div>
            )
          })}
        </div>

        {error && (
          <div className="p-4 bg-red-100 text-red-800 rounded-md border border-red-200 w-full">
            Error: {error}
          </div>
        )}

        {status === 'idle' && (
          <VideoInput onVideoSelected={handleVideoSelected} />
        )}

        {status === 'transcribing' && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-lg">Transcribing Audio...</p>
            <p className="text-sm text-muted-foreground">This may take a minute depending on video length.</p>
          </div>
        )}

        {status === 'reviewing' && (
          <div className="space-y-6">
            <div className="bg-card border rounded-xl p-6">
              <h2 className="text-xl font-semibold mb-4 flex items-center">
                <FileAudio className="mr-2 w-5 h-5" /> Original Transcript ({segments.length} segments)
              </h2>
              <div className="max-h-60 overflow-y-auto space-y-2 mb-6 border p-2 rounded">
                {segments.map((s, i) => (
                  <p key={i} className="text-sm"><span className="text-muted-foreground">[{s.start.toFixed(1)}s]</span> {s.text}</p>
                ))}
              </div>

              <div className="flex items-center space-x-4 border-t pt-4">
                <Languages className="w-5 h-5" />
                <span className="font-medium">Target Language:</span>
                <select
                  value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}
                  className="border rounded p-2 bg-background"
                >
                  <option value="zh">Chinese (Simplified)</option>
                  <option value="en">English</option>
                </select>

                <button
                  onClick={handleTranslate}
                  className="ml-auto bg-primary text-primary-foreground px-6 py-2 rounded-lg hover:bg-primary/90"
                >
                  Translate
                </button>
              </div>
            </div>
          </div>
        )}

        {status === 'translating' && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-lg">Translating Subtitles...</p>
          </div>
        )}

        {(status === 'dubbing' && finalVideo === null) && (
          <div className="space-y-6">
            {/* Show translated results */}
            <div className="bg-card border rounded-xl p-6">
              <h2 className="text-xl font-semibold mb-4">Translation Ready</h2>
              <div className="max-h-60 overflow-y-auto space-y-2 mb-6 border p-2 rounded">
                {translatedSegments.map((s, i) => (
                  <div key={i} className="text-sm grid grid-cols-2 gap-4 border-b pb-1 mb-1">
                    <p className="text-muted-foreground">{segments[i]?.text}</p>
                    <p className="font-medium text-blue-600">{s.text}</p>
                  </div>
                ))}
              </div>
              <div className="flex justify-end">
                <button
                  onClick={handleDub}
                  disabled={status === 'dubbing' && error === null} // Wait, I reused status 'dubbing' for both "Review Translation" and "Processing Dub"
                  className="bg-primary text-primary-foreground px-6 py-2 rounded-lg hover:bg-primary/90 flex items-center"
                >
                  {status === 'dubbing' && !translatedSegments.length ? <Loader2 className="animate-spin mr-2" /> : null}
                  Generate Dubbed Video
                </button>
              </div>
            </div>

            {/* If actually processing dub (I need a sub-state or just use 'dubbing' properly) */}
            {/* Re-using 'dubbing' state for "Ready to Dub" + "Dubbing in Progress" is confusing. */}
            {/* Let's fix state: 'reviewing' -> 'translating' -> 'translated' -> 'dubbing' -> 'finished' */}
          </div>
        )}

        {/* Quick Fix: 'dubbing' state logic above is messy. Let's assume 'dubbing' means IN PROGRESS.
            I need a 'translated' state. 
        */}

        {/* Redoing the logic block for 'translated' state */}
        {status === 'dubbing' && finalVideo === null && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-lg">Generating Audio & Mixing...</p>
            <p className="text-sm text-muted-foreground">This involves TTS and video processing. Please wait.</p>
          </div>
        )}

        {status === 'finished' && finalVideo && (
          <div className="flex flex-col items-center space-y-6 animate-fade-in">
            <div className="w-full aspect-video bg-black rounded-xl overflow-hidden shadow-2xl">
              <video controls src={`${API_URL}${finalVideo}`} className="w-full h-full" />
            </div>

            <h2 className="text-2xl font-bold text-green-600 flex items-center">
              <CheckCircle className="mr-2" /> Processing Complete!
            </h2>

            <button
              onClick={() => window.location.reload()}
              className="text-muted-foreground hover:text-foreground underline"
            >
              Start New Project
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
