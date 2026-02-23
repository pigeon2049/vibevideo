import edge_tts
import os
import hashlib
import logging
import re
import tenacity
from typing import List, Dict, Optional
from app.core.config import settings


logger = logging.getLogger("vibe-video.tts")

class TTSService:
    def __init__(self):
        self.default_voice_en = settings.DEFAULT_VOICE_EN
        self.default_voice_zh = settings.DEFAULT_VOICE_ZH
        # Regex for alphanumeric characters or Chinese characters
        self.speakable_pattern = re.compile(r'[\w\u4e00-\u9fff]')

    def is_speakable(self, text: str) -> bool:
        """Check if the text contains any actual characters to speak."""
        if not text:
            return False
        return bool(self.speakable_pattern.search(text))

    async def generate_speech(self, text: str, voice: Optional[str] = None, output_file: Optional[str] = None) -> str:
        if not self.is_speakable(text):
            logger.info(f"[TTS] Text is not speakable (punctuation/whitespace only), skipping: '{text[:20]}...'")
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

        @tenacity.retry(
            stop=tenacity.stop_after_attempt(3),
            wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
            retry=tenacity.retry_if_exception_type(edge_tts.exceptions.NoAudioReceived),
            before_sleep=lambda retry_state: logger.warning(
                f"TTS Retry attempt {retry_state.attempt_number} for text: '{text[:30]}...'"
            )
        )
        async def save_audio():
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_file)

        try:
            logger.info(f"Generating speech for: {text[:20]}... with voice {voice}")
            await save_audio()
            return output_file
        except Exception as e:
            logger.error(f"TTS Generation Error for text '{text}': {e}")
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
