import { useEffect } from 'react'
import { VideoInput } from './components/VideoInput'
import { Header } from './components/Header'
import { DubbingStep } from './components/DubbingStep'
import { FinishedPlayer } from './components/FinishedPlayer'
import { TranslationWorkspace } from './components/TranslationWorkspace'
import { useTranslationPipeline } from './hooks/useTranslationPipeline'

function App() {
  const {
    status, setStatus,
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
  } = useTranslationPipeline();

  const API_URL = "http://localhost:8000";

  useEffect(() => {
    const savedProjectId = localStorage.getItem('vibe_project_id');
    if (savedProjectId && status === 'idle') {
      restoreProject(savedProjectId);
    }
  }, [restoreProject, status]);

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
            onUpdateTranslation={handleUpdateTranslation}
          />
        )}

        {status === 'dubbing' && <DubbingStep progress={dubbingProgress} paragraphs={dubbingParagraphs} baseUrl={API_URL} />}

        {status === 'finished' && finalVideo && (
          <FinishedPlayer
            videoUrl={`${API_URL}${finalVideo}`}
            onBack={() => setStatus('translated')}
          />
        )}
      </div>
    </div>
  )
}

export default App