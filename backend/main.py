from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os
import shutil
import uuid

from services import downloader, transcriber, translator, tts, audio_processor
from utils.file_manager import TEMP_DIR, OUTPUT_DIR, VIDEO_DIR

app = FastAPI(title="Vibe Video API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files to serve generated videos
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")

# --- Pydantic Models ---

class DownloadRequest(BaseModel):
    url: str

class TranscribeRequest(BaseModel):
    video_path: str
    language: Optional[str] = None

class Segment(BaseModel):
    start: float
    end: float
    text: str
    audio_file: Optional[str] = None

class TranslateRequest(BaseModel):
    segments: List[Segment]
    target_language: str

class DubRequest(BaseModel):
    video_path: str
    segments: List[Segment]
    voice: str
    background_volume: float = 0.1

# --- Endpoints ---

@app.get("/")
async def root():
    return {"message": "Vibe Video API is running"}

@app.post("/download")
async def download_video_endpoint(request: DownloadRequest):
    try:
        result = downloader.download_video(request.url)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def upload_video_endpoint(file: UploadFile = File(...)):
    try:
        filename = f"{uuid.uuid4()}_{file.filename}"
        file_path = os.path.join(VIDEO_DIR, filename)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return {
            "title": file.filename,
            "path": file_path,
            "original_url": None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/transcribe")
async def transcribe_endpoint(request: TranscribeRequest):
    try:
        if not os.path.exists(request.video_path):
            raise HTTPException(status_code=404, detail="Video file not found")
        
        # Extract audio first for faster transcription? 
        # Whisper can handle video directly (via ffmpeg), but let's just pass path.
        segments = transcriber.transcribe_audio(request.video_path, request.language)
        return {"segments": segments}
    except Exception as e:
        print(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/translate")
async def translate_endpoint(request: TranslateRequest):
    try:
        # Pydantic model to dict
        segments_dict = [s.dict() for s in request.segments]
        translated = translator.translate_segments(segments_dict, request.target_language)
        return {"segments": translated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/dub")
async def dub_endpoint(request: DubRequest):
    try:
        # 1. Generate Speech
        segments_dict = [s.dict() for s in request.segments]
        segments_with_audio = await tts.generate_speech_for_segments(segments_dict, request.voice)
        
        # 2. Concatenate speech segments into one track (complex, easier to use ffmpeg filter or moviepy)
        # For simplicity MVP: process each segment? No, we need a single audio track synced.
        # Let's create a silence-padded audio track.
        
        # Actually, let's implement a simple "stitcher" here or in audio_processor
        # For MVP, let's use a simplified approach:
        # We will create a full length audio file.
        
        # Isolate original audio and separate vocals
        print("Isolating original audio...")
        original_audio = audio_processor.isolate_audio(request.video_path)
        
        print("Separating vocals...")
        separated = audio_processor.separate_vocals(original_audio)
        background_audio = separated["background"]
        
        # Generate full TTS track
        # This is tricky without exact timing. Text length != Audio length.
        # We might need to speed up/slow down audio to fit the segment duration.
        # For this MVP, we will just place the audio at the start time.
        
        # TODO: Ideally should be in audio_processor. 
        # But let's build the ffmpeg command here or add a specific function in audio_processor.
        
        # Let's add a function "create_dub_track" in audio_processor that takes segments with audio files
        # and creates a single mixed wav file.
        
        # For now, let's assume we implement `audio_processor.create_dub_track`
        # I'll update audio_processor next to support this.
        
        # Placeholder: Return error for now as we need that function.
        # Or better: I will implement `audio_processor.mix_segments` in a separate step or right now.
        
        # Use a temporary implementation for now:
        # Just return the background audio as "dubbed" to test flow.
        final_video = audio_processor.merge_audio_video(request.video_path, background_audio)
        
        return {
            "video_path": final_video, 
            "url": f"/output/{os.path.basename(final_video)}"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
