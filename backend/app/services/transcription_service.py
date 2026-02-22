import os
import asyncio
import subprocess
import re
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Optional
from app.core.config import settings

logger = logging.getLogger("vibe-video.transcription")

class SubtitleProcessor:
    def __init__(self, min_chars=12, max_chars=40, max_silence=0.8):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.max_silence = max_silence
        self.punctuations = set("，。！？；、,.!?;")
        self.hanging_words = {"the", "a", "an", "to", "of", "for", "with", "on", "at", "by", "from", "in", "and", "or", "but"}
        self.words_buffer = []  
        self.processed_texts = [] 

    def add_segment(self, segment_dict: Dict) -> List[Dict]:
        words = segment_dict.get("words", [])
        if not words:
            text = segment_dict["text"].strip()
            if not text: return []
            words = [{"text": text, "start": segment_dict["start"], "end": segment_dict["end"]}]

        results = []
        for w in words:
            word_text = w["text"]
            start = w["start"]
            end = w["end"]
            
            if self.words_buffer:
                last_end = self.words_buffer[-1]["end"]
                if start - last_end > self.max_silence:
                    results.extend(self.flush())
            
            self.words_buffer.append({"text": word_text, "start": start, "end": end})
            results.extend(self._process_buffer())
            
        return results

    def _process_buffer(self) -> List[Dict]:
        results = []
        while True:
            full_text = "".join([w["text"] for w in self.words_buffer]).strip()
            if len(full_text) < self.min_chars:
                break
            
            split_idx = self._find_split_point()
            if split_idx != -1:
                chunk = self.words_buffer[:split_idx]
                self.words_buffer = self.words_buffer[split_idx:]
                seg = self._make_segment(chunk)
                
                if self._is_looping(seg["text"]):
                    continue
                
                results.append(seg)
                self.processed_texts.append(seg["text"])
                if len(self.processed_texts) > 10: self.processed_texts.pop(0)
            else:
                break
        return results

    def _find_split_point(self) -> int:
        full_text = "".join([w["text"] for w in self.words_buffer])
        if not full_text: return -1
        
        current_len = 0
        punc_idx = -1
        for i, w in enumerate(self.words_buffer):
            current_len += len(w["text"])
            if current_len >= self.min_chars:
                clean_w = w["text"].strip()
                if clean_w and clean_w[-1] in self.punctuations:
                    if clean_w[-1] in ",." and i + 1 < len(self.words_buffer) and self.words_buffer[i+1]["text"].strip()[:1].isdigit():
                        continue
                    punc_idx = i + 1
                    if current_len <= self.max_chars:
                        return punc_idx

        if current_len > self.max_chars:
            temp_len = current_len
            for i in range(len(self.words_buffer) - 1, 0, -1):
                w = self.words_buffer[i]
                prev_w = self.words_buffer[i-1]
                temp_len -= len(w["text"])
                if temp_len <= self.max_chars:
                    clean_prev = prev_w["text"].strip().lower().strip(".,!?")
                    if clean_prev not in self.hanging_words:
                        return i
            
            temp_len = 0
            for i, w in enumerate(self.words_buffer):
                temp_len += len(w["text"])
                if temp_len >= self.max_chars:
                    return i + 1
        return -1

    def _is_looping(self, text: str) -> bool:
        if not text: return False
        clean_text = text.strip().lower()
        for p in self.processed_texts:
            if clean_text == p.strip().lower():
                return True
        words = clean_text.split()
        if len(words) > 4:
            word_counts = {}
            for w in words:
                word_counts[w] = word_counts.get(w, 0) + 1
            max_repeat = max(word_counts.values())
            if max_repeat / len(words) > 0.7:
                return True
        return False

    def flush(self) -> List[Dict]:
        results = []
        if self.words_buffer:
            seg = self._make_segment(self.words_buffer)
            if seg["text"] and not self._is_looping(seg["text"]):
                results.append(seg)
            self.words_buffer = []
        return results
        
    def _make_segment(self, chunk: List[Dict]) -> Dict:
        text = "".join([w["text"] for w in chunk]).strip()
        text = re.sub(r'\s+', ' ', text)
        return {
            "id": str(uuid.uuid4()),
            "start": round(chunk[0]["start"], 3),
            "end": round(chunk[-1]["end"], 3),
            "text": text
        }

import json
import tempfile
from typing import Union

def format_ffmpeg_filter_path(path: Union[str, Path]) -> str:
    """
    Standardize paths for FFmpeg filters (especially on Windows).
    - Uses forward slashes
    - Escapes colons (drive letters)
    - Escapes single quotes
    """
    p = str(Path(path).absolute()).replace('\\', '/')
    p = p.replace(':', '\\:')
    p = p.replace("'", "'\\\\''")
    return p

import hashlib

def get_file_hash(path: Union[str, Path]) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        # Read in chunks to handle large files
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

class TranscriptionService:
    def __init__(self):
        # We no longer need the model singleton as it's handled by FFmpeg
        pass

    async def _get_model(self):
        # Deprecated: FFmpeg handles model loading
        pass

    async def extract_audio(self, video_path: str, start_time: float = 0.0) -> str:
        output_path = settings.TEMP_DIR / f"{Path(video_path).stem}_{start_time}.wav"
        
        command = [
            "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"
        ]
        if start_time > 0:
            command.extend(["-ss", str(start_time)])
        command.append(str(output_path))

        logger.info(f"Extracting audio from {video_path} starting at {start_time}")
        process = await asyncio.create_subprocess_exec(
            str(settings.FFMPEG_PATH), *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await process.wait()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg audio extraction failed with code {process.returncode}")
            raise subprocess.CalledProcessError(process.returncode, [str(settings.FFMPEG_PATH)] + command)
            
        return str(output_path)

    async def transcribe(self, audio_path: str, resume_start: float = 0.0, progress_callback=None) -> List[Dict]:
        processor = SubtitleProcessor()
        
        model_path = settings.MODELS_DIR / settings.WHISPER_MODEL
        vad_path = settings.MODELS_DIR / settings.VAD_MODEL
        
        if not model_path.exists():
            logger.error(f"Whisper model not found: {model_path}")
            raise FileNotFoundError(f"Whisper model not found: {model_path}")

        # Use a hash of the audio file to check for cached results
        audio_hash = get_file_hash(audio_path)
        cache_json_path = settings.CACHE_DIR / f"whisper_{audio_hash}.json"
        
        if cache_json_path.exists():
            logger.info(f"Using cached transcription results found at {cache_json_path}")
            tmp_json_path = cache_json_path
            need_transcribe = False
        else:
            # Use a more predictable path and keep it for debugging as requested
            tmp_json_path = settings.TEMP_DIR / f"raw_transcription_{uuid.uuid4().hex[:8]}.json"
            need_transcribe = True

        try:
            if need_transcribe:
                model_path_esc = format_ffmpeg_filter_path(model_path)
                tmp_json_path_esc = format_ffmpeg_filter_path(tmp_json_path)
            
                whisper_filter = f"whisper=model='{model_path_esc}'"
                whisper_filter += ":language=auto:format=json"
                whisper_filter += f":destination='{tmp_json_path_esc}'"
                whisper_filter += ":use_gpu=true:gpu_device=0:queue=10"
                
                if vad_path.exists():
                    vad_path_esc = format_ffmpeg_filter_path(vad_path)
                    whisper_filter += f":vad_model='{vad_path_esc}'"
                
                command = [
                    str(settings.FFMPEG_PATH), "-y",
                    "-i", audio_path,
                    "-vn",
                    "-af", whisper_filter,
                    "-f", "null", "-"
                ]
                
                import subprocess
                logger.info(f"Starting FFmpeg transcription for: {audio_path}")
                logger.info("Starting FFmpeg via subprocess.Popen (Robust Windows workaround)...")
                try:
                    # Use subprocess.Popen which is more reliable on Windows regardless of event loop type
                    process = subprocess.Popen(
                        command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        bufsize=1,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    logger.info(f"FFmpeg process started with PID {process.pid}")
                except Exception as e:
                    logger.error(f"Failed to start FFmpeg process via Popen: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise

                # Read stderr for progress updates
                duration_s = 0
                async def read_stderr():
                    nonlocal duration_s
                    loop = asyncio.get_running_loop()
                    while True:
                        # Use run_in_executor to read from pipe without blocking the loop
                        line = await loop.run_in_executor(None, process.stderr.readline)
                        if not line:
                            break
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if line_str:
                            # Print to console for immediate visibility as requested
                            print(f"[FFmpeg] {line_str}", flush=True)
                            logger.info(f"FFmpeg: {line_str}")
                        
                        # Extract time=00:00:00.00
                        if "time=" in line_str:
                            import re
                            match = re.search(r"time=(\d+:\d+:\d+\.\d+)", line_str)
                            if match and progress_callback:
                                time_str = match.group(1)
                                await progress_callback(time_str)
                        
                        if "Duration:" in line_str and duration_s == 0:
                            # Extract Duration: 00:32:13.18
                            import re
                            match = re.search(r"Duration:\s*(\d+:\d+:\d+\.\d+)", line_str)
                            if match:
                                t = match.group(1).split(':')
                                duration_s = int(t[0])*3600 + int(t[1])*60 + float(t[2])

                # Start reading task
                stderr_task = asyncio.create_task(read_stderr())
                
                # Wait for process to exit
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, process.wait)
                
                # Ensure reading completes
                await stderr_task
                
                if process.returncode != 0:
                    logger.error(f"FFmpeg error: {process.returncode}")
                    return []

                if not os.path.exists(tmp_json_path):
                    logger.error(f"FFmpeg did not create output JSON at {tmp_json_path}")
                    return []

                # Copy to cache for future use
                try:
                    import shutil
                    shutil.copy2(tmp_json_path, cache_json_path)
                    logger.info(f"Transcription results cached at {cache_json_path}")
                except Exception as e:
                    logger.warning(f"Failed to cache transcription results: {e}")

                logger.info(f"Full raw transcription saved at: {tmp_json_path}")
            else:
                # If using cache, just log it
                logger.info(f"Loading transcription from cache: {tmp_json_path}")

            raw_segments = []
            try:
                with open(tmp_json_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Robustly parse multiple JSON objects (FFmpeg whisper filter format)
                decoder = json.JSONDecoder()
                pos = 0
                while pos < len(content):
                    # Skip whitespace
                    while pos < len(content) and content[pos].isspace():
                        pos += 1
                    if pos >= len(content):
                        break
                    
                    try:
                        obj, next_pos = decoder.raw_decode(content, pos)
                        if isinstance(obj, dict):
                            if "segments" in obj:
                                raw_segments.extend(obj["segments"])
                            else:
                                raw_segments.append(obj)
                        elif isinstance(obj, list):
                            raw_segments.extend(obj)
                        pos = next_pos
                    except json.JSONDecodeError:
                        # Fallback to regex for this segment (handles unescaped quotes)
                        # Extract the approximate object content
                        # We look for something that starts with { and ends with } on roughly the same line/area
                        match = re.search(r'\{"start":(\d+),"end":(\d+),"text":"(.*)"\s*\}', content[pos:])
                        if match:
                            start = int(match.group(1))
                            end = int(match.group(2))
                            text = match.group(3)
                            raw_segments.append({"start": start, "end": end, "text": text})
                            pos += match.end()
                        else:
                            # If regex also fails, we must skip or break to avoid infinite loop
                            logger.warning(f"Could not parse transcription segment at pos {pos}, skipping...")
                            # Find next potential start
                            next_start = content.find('{"start":', pos + 1)
                            if next_start == -1:
                                break
                            pos = next_start
            except Exception as e:
                logger.error(f"Error reading/parsing transcription JSON: {e}")
            
            final_processed = []
            for seg in raw_segments:
                seg_data = {
                    "start": seg.get("start", 0) / 1000.0 if seg.get("start", 0) > 100 else seg.get("start", 0),
                    "end": seg.get("end", 0) / 1000.0 if seg.get("end", 0) > 100 else seg.get("end", 0),
                    "text": seg.get("text", "").strip(),
                    "words": []
                }
                
                seg_data["start"] += resume_start
                seg_data["end"] += resume_start
                
                if not seg_data["text"]:
                    continue
                    
                final_processed.extend(processor.add_segment(seg_data))
            
            final_processed.extend(processor.flush())
            return final_processed
            
        finally:
            # Keep the file for debugging if it was just created
            if need_transcribe:
                pass 
                # if os.path.exists(tmp_json_path):
                #     try:
                #         os.unlink(tmp_json_path)
                #     except:
                #         pass

transcription_service = TranscriptionService()
