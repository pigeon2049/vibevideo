import edge_tts
import os
import hashlib
import logging
from typing import List, Dict, Optional
from app.core.config import settings

logger = logging.getLogger("vibe-video.tts")

class TTSService:
    def __init__(self):
        self.default_voice_en = settings.DEFAULT_VOICE_EN
        self.default_voice_zh = settings.DEFAULT_VOICE_ZH

    async def generate_speech(self, text: str, voice: Optional[str] = None, output_file: Optional[str] = None) -> str:
        if not text.strip():
            return ""

        # Use default voice if none provided or if "default" string passed
        if not voice or (isinstance(voice, str) and voice.lower() == "default"):
            voice = self.default_voice_zh
            logger.info(f"[TTS] No voice specified or 'default', using default: {voice}")
        else:
            logger.info(f"[TTS] Using specified voice: {voice}")

        if not output_file:
            text_hash = hashlib.md5(f"{text}_{voice}".encode()).hexdigest()
            output_file = str(settings.AUDIO_DIR / f"tts_{text_hash}.mp3")
            
        if os.path.exists(output_file):
            logger.info(f"Using cached audio for: {text[:20]}...")
            return output_file

        try:
            logger.info(f"Generating speech for: {text[:20]}... with voice {voice}")
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_file)
            return output_file
        except Exception as e:
            logger.error(f"TTS Generation Error: {e}")
            raise

    async def generate_speech_for_segments(self, segments: List[Dict], voice: str):
        for segment in segments:
            text = segment.get("text", "")
            if text.strip():
                audio_path = await self.generate_speech(text, voice)
                segment["audio_file"] = audio_path
            else:
                segment["audio_file"] = None
        return segments

tts_service = TTSService()
