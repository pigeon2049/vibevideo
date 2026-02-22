import os
import subprocess
import logging
import math
import shutil
import uuid
from pathlib import Path
from typing import List, Dict, Optional
from pydub import AudioSegment
from app.core.config import settings

logger = logging.getLogger("vibe-video.audio")

class AudioService:
    def __init__(self):
        self.ffmpeg_exe = str(settings.FFMPEG_PATH)
        if not os.path.exists(self.ffmpeg_exe):
            logger.warning(f"FFMPEG not found at {self.ffmpeg_exe}, falling back to system ffmpeg")
            self.ffmpeg_exe = "ffmpeg"
        
        # Configure pydub
        AudioSegment.converter = self.ffmpeg_exe
        ffprobe_exe = os.path.join(os.path.dirname(self.ffmpeg_exe), "ffprobe.exe" if os.name == "nt" else "ffprobe")
        if os.path.exists(ffprobe_exe):
            AudioSegment.ffprobe = ffprobe_exe

    def isolate_audio(self, video_path: str) -> str:
        """Extracts audio from video."""
        output_path = settings.TEMP_DIR / f"{Path(video_path).stem}_full.wav"
        
        cmd = [
            self.ffmpeg_exe, "-y",
            "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            str(output_path)
        ]
        
        logger.info(f"Isolating audio from {video_path}")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(output_path)

    def separate_vocals(self, audio_path: str) -> Dict[str, str]:
        """Separates vocals using Demucs."""
        model = "htdemucs"
        output_dir = settings.TEMP_DIR / "separated"
        
        cmd = [
            "demucs", 
            "-n", model,
            "--two-stems=vocals",
            "-o", str(output_dir),
            audio_path
        ]
        
        logger.info(f"Running Demucs on {audio_path}")
        subprocess.run(cmd, check=True)
        
        filename = Path(audio_path).stem
        base_dir = output_dir / model / filename
        
        results = {
            "vocals": str(base_dir / "vocals.wav"),
            "background": str(base_dir / "no_vocals.wav")
        }
        
        if not os.path.exists(results["background"]):
            logger.error(f"Demucs output not found at {results['background']}")
            # Fallback: if separation fails, use the original audio as background (not ideal but better than crashing)
            return {"vocals": audio_path, "background": audio_path}
            
        return results

    def merge_audio_video(
        self, 
        video_path: str, 
        background_audio: str, 
        tts_segments: List[Dict], 
        bg_volume: float = 0.1, 
        subtitle_path: Optional[str] = None
    ) -> str:
        """Merges video with mixed background audio and TTS segments."""
        
        logger.info("Loading background audio for mixing...")
        bg_track = AudioSegment.from_file(background_audio)
        
        if bg_volume < 1.0:
            db_change = 20 * math.log10(max(bg_volume, 0.001))
            bg_track = bg_track + db_change
            
        logger.info(f"Mixing {len(tts_segments)} TTS segments...")
        for seg in tts_segments:
            audio_file = seg.get("audio_file")
            if audio_file and os.path.exists(audio_file):
                try:
                    tts_track = AudioSegment.from_file(audio_file)
                    pos_ms = int(seg.get("start", 0) * 1000)
                    
                    # Check if audio needs speed adjustment
                    target_duration_ms = int((seg.get("end", 0) - seg.get("start", 0)) * 1000)
                    actual_duration_ms = len(tts_track)
                    
                    if actual_duration_ms > target_duration_ms and target_duration_ms > 0:
                        speed_factor = actual_duration_ms / target_duration_ms
                        logger.info(f"Segment {seg.get('id')} duration {actual_duration_ms}ms > target {target_duration_ms}ms. Speeding up by {speed_factor:.2f}x")
                        
                        # Apply speed adjustment
                        try:
                            sped_up_file = self._adjust_audio_speed(audio_file, speed_factor)
                            tts_track = AudioSegment.from_file(sped_up_file)
                            # Update duration for ducking
                            actual_duration_ms = len(tts_track)
                        except Exception as e:
                            logger.error(f"Failed to adjust speed for segment {seg.get('id')}: {e}")
                    
                    # Implementation of Ducking:
                    # 1. Calculate duration of the speech
                    duration_ms = actual_duration_ms
                    
                    # 2. Extract the part of background music that overlaps with speech
                    # (Ensure we don't go out of bounds)
                    overlap_end = min(pos_ms + duration_ms, len(bg_track))
                    if pos_ms < len(bg_track):
                        # Reduce volume of this section by ~12dB
                        ducked_section = bg_track[pos_ms:overlap_end] - 12
                        
                        # Apply fades to make the volume change smooth
                        ducked_section = ducked_section.fade_in(50).fade_out(50)
                        
                        # Put it back into the background track
                        bg_track = bg_track[:pos_ms] + ducked_section + bg_track[overlap_end:]
                    
                    # 3. Finally overlay the speech
                    bg_track = bg_track.overlay(tts_track, position=pos_ms)
                except Exception as e:
                    logger.error(f"Failed to overlay segment {seg.get('id', 'unknown')}: {e}")
                    
        mixed_audio_path = settings.TEMP_DIR / f"mixed_{uuid.uuid4().hex[:8]}.wav"
        logger.info("Exporting mixed audio track...")
        
        # Apply more sophisticated mixing if possible, or just export the layered track
        # For professional results, we often "duck" the background music 
        # when speech is present.
        
        bg_track.export(str(mixed_audio_path), format="wav")
        
        output_path = settings.OUTPUT_DIR / f"{Path(video_path).stem}_final.mp4"
        
        cmd = [
            self.ffmpeg_exe, "-y",
            "-i", video_path,
            "-i", str(mixed_audio_path)
        ]

        if subtitle_path and os.path.exists(subtitle_path):
            escaped_sub_path = subtitle_path.replace('\\', '/')
            if len(escaped_sub_path) > 1 and escaped_sub_path[1] == ':':
                escaped_sub_path = escaped_sub_path[0] + '\\:' + escaped_sub_path[2:]
            
            logger.info(f"Adding subtitles filter with path: {escaped_sub_path}")
            cmd.extend(["-vf", f"subtitles='{escaped_sub_path}'"])
        else:
            cmd.extend(["-c:v", "copy"])

        cmd.extend([
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output_path)
        ])
        
        logger.info("Running ffmpeg to merge video and audio...")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        return str(output_path)

    def mix_audio_tracks(self, background_path: str, speech_path: str, background_volume: float = 0.3) -> str:
        """
        Mixes background audio (at lower volume) with speech audio using ffmpeg filter_complex.
        (Preserved from services/audio_processor.py)
        """
        output_path = settings.TEMP_DIR / f"mixed_{uuid.uuid4().hex[:8]}.wav"
        
        filter_complex = f"[0:a]volume={background_volume}[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first"
        
        cmd = [
            self.ffmpeg_exe, "-y",
            "-i", background_path,
            "-i", speech_path,
            "-filter_complex", filter_complex,
            str(output_path)
        ]
        
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(output_path)

    def _adjust_audio_speed(self, input_path: str, speed_factor: float) -> str:
        """Adjusts audio speed using ffmpeg atempo filter."""
        output_path = settings.TEMP_DIR / f"speedup_{uuid.uuid4().hex[:8]}.wav"
        
        # atempo filter only supports 0.5 to 2.0. 
        # For factors outside this range, we need to chain filters.
        filters = []
        remaining_speed = speed_factor
        
        while remaining_speed > 2.0:
            filters.append("atempo=2.0")
            remaining_speed /= 2.0
        
        if remaining_speed < 0.5:
            while remaining_speed < 0.5:
                filters.append("atempo=0.5")
                remaining_speed /= 0.5
        
        filters.append(f"atempo={remaining_speed}")
        filter_str = ",".join(filters)
        
        cmd = [
            self.ffmpeg_exe, "-y",
            "-i", input_path,
            "-filter:a", filter_str,
            str(output_path)
        ]
        
        logger.info(f"Speeding up audio: {input_path} with filters: {filter_str}")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(output_path)

audio_service = AudioService()

