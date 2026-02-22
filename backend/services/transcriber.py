import os
import asyncio
import threading
import subprocess
import uuid
import re
from pathlib import Path
from fastapi import APIRouter, WebSocket
from db.database import SessionLocal
from db.models import Segment, Project
from app.services.transcription_service import transcription_service
from app.services.translation_service import translation_service

router = APIRouter()

# ==================================================
# 路径配置
# ==================================================
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_DIR = PROJECT_ROOT / "models" / "large-v3"
FFMPEG_PATH = PROJECT_ROOT / "backend" / "bin" / "ffmpeg.exe"
TEMP_DIR = PROJECT_ROOT / "backend" / "temp"

TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ==================================================
# 音频提取
# ==================================================
def extract_audio(video_path: str, start_time: float = 0.0) -> str:
    output_path = TEMP_DIR / f"{Path(video_path).stem}_{start_time}.wav"
    if not FFMPEG_PATH.exists():
        raise RuntimeError(f"ffmpeg not found: {FFMPEG_PATH}")

    command = [
        str(FFMPEG_PATH), "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"
    ]
    if start_time > 0:
        command.extend(["-ss", str(start_time)])
    command.append(str(output_path))

    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(output_path)

# ==================================================
# ✨ 优化后的断句引擎
# ==================================================
class SubtitleProcessor:
    """
    负责将 Whisper 的原始 Segment/Word 进一步规范化。
    基于单词和实际时间戳进行断句与合并，避免将短语切断（例如不让句子以 the, a, to 等结尾）。
    """
    def __init__(self, min_chars=12, max_chars=40, max_silence=0.8):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.max_silence = max_silence
        self.punctuations = set("，。！？；、,.!?;")
        self.hanging_words = {"the", "a", "an", "to", "of", "for", "with", "on", "at", "by", "from", "in", "and", "or", "but"}
        self.words_buffer = []  # List of dict: {"text": str, "start": float, "end": float}
        self.processed_texts = [] # For duplicate detection/loop prevention

    def add_segment(self, segment_dict):
        """
        Whisper segment contains a list of words with timestamps.
        """
        words = segment_dict.get("words", [])
        if not words:
            # Fallback if no word timestamps
            text = segment_dict["text"].strip()
            if not text: return []
            words = [{"text": text, "start": segment_dict["start"], "end": segment_dict["end"]}]

        results = []
        
        for w in words:
            word_text = w["text"]
            start = w["start"]
            end = w["end"]
            
            # 1. 检测停顿
            if self.words_buffer:
                last_end = self.words_buffer[-1]["end"]
                if start - last_end > self.max_silence:
                    results.extend(self.flush())
            
            # 2. 幻听/循环过滤 (Hallucination/Loop Filter)
            # 如果单词在该 segment 里特别短且重复，可能是幻听
            clean_word = word_text.strip().lower().strip(".,!?")
            if len(clean_word) > 2: # 忽略太短的词
                duration = end - start
                # 语速过快检测 (e.g. 50 chars/sec is inhuman for long chunks, but context here is single words)
                # Word-level speed is less reliable than segment-level, but if duration is 0, it's a bug
                if duration < 0.01: duration = 0.01 
            
            self.words_buffer.append({"text": word_text, "start": start, "end": end})
            results.extend(self._process_buffer())
            
        return results

    def _process_buffer(self):
        results = []
        while True:
            full_text = "".join([w["text"] for w in self.words_buffer]).strip()
            
            if len(full_text) < self.min_chars:
                break
            
            # 找到合适的断点
            split_idx = self._find_split_point()
            
            if split_idx != -1:
                chunk = self.words_buffer[:split_idx]
                self.words_buffer = self.words_buffer[split_idx:]
                seg = self._make_segment(chunk)
                
                # 防重复/防循环过滤器
                if self._is_looping(seg["text"]):
                    # print(f"🚫 Dropping detected loop segment: {seg['text']}")
                    continue
                
                results.append(seg)
                self.processed_texts.append(seg["text"])
                if len(self.processed_texts) > 10: self.processed_texts.pop(0)
            else:
                break
                
        return results

    def _find_split_point(self):
        """
        根据标点、长度和 'hanging words' 寻找最佳断点。
        """
        full_text = "".join([w["text"] for w in self.words_buffer])
        if not full_text: return -1
        
        # 1. 寻找标点
        # 范围：从 min_chars 之后到 max_chars 之前
        current_len = 0
        punc_idx = -1
        
        for i, w in enumerate(self.words_buffer):
            current_len += len(w["text"])
            if current_len >= self.min_chars:
                # 检查是否以标点结尾
                clean_w = w["text"].strip()
                if clean_w and clean_w[-1] in self.punctuations:
                    # 避免数字中间的 , .
                    if clean_w[-1] in ",." and i + 1 < len(self.words_buffer) and self.words_buffer[i+1]["text"].strip()[:1].isdigit():
                        continue
                    punc_idx = i + 1
                    # 如果在 max_chars 以内，这就是个完美的断点
                    if current_len <= self.max_chars:
                        return punc_idx

        # 2. 如果没找到标点，或者标点太远，尝试寻找空格/词界，且避开 hanging words
        if current_len > self.max_chars:
            # 倒着找一个不是 hanging word 的位置
            temp_len = current_len
            for i in range(len(self.words_buffer) - 1, 0, -1):
                w = self.words_buffer[i]
                prev_w = self.words_buffer[i-1]
                temp_len -= len(w["text"])
                
                if temp_len <= self.max_chars:
                    # 检查 prev_w 是不是以 'hanging_words' 结尾
                    clean_prev = prev_w["text"].strip().lower().strip(".,!?")
                    if clean_prev not in self.hanging_words:
                        return i
            
            # 实在没办法，就只能在 max_chars 左右切了
            temp_len = 0
            for i, w in enumerate(self.words_buffer):
                temp_len += len(w["text"])
                if temp_len >= self.max_chars:
                    return i + 1
                    
        return -1

    def _is_looping(self, text):
        """
        检测该段是否是之前内容的重复 (Hallucination prevention)
        """
        if not text: return False
        clean_text = text.strip().lower()
        
        # 1. 检查是否完全相同
        for p in self.processed_texts:
            if clean_text == p.strip().lower():
                return True
        
        # 2. 检查是否有大量重复单词 (e.g. "Incogni Incogni Incogni")
        words = clean_text.split()
        if len(words) > 4:
            word_counts = {}
            for w in words:
                word_counts[w] = word_counts.get(w, 0) + 1
            max_repeat = max(word_counts.values())
            if max_repeat / len(words) > 0.7:
                return True
                
        return False

    def flush(self):
        results = []
        if self.words_buffer:
            seg = self._make_segment(self.words_buffer)
            if seg["text"] and not self._is_looping(seg["text"]):
                results.append(seg)
            self.words_buffer = []
        return results
        
    def _make_segment(self, chunk):
        text = "".join([w["text"] for w in chunk]).strip()
        # 过滤掉多余空格和特殊字符
        text = re.sub(r'\s+', ' ', text)
        
        return {
            "id": str(uuid.uuid4()),
            "start": round(chunk[0]["start"], 3),
            "end": round(chunk[-1]["end"], 3),
            "text": text
        }

# Removed transcribe_and_process and format_ffmpeg_filter_path as they are now in transcription_service.py

# ==================================================
# WebSocket 转录
# ==================================================
@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    await websocket.accept()
    db = SessionLocal()

    try:
        data = await websocket.receive_json()
        video_path = data.get("video_path")
        project_id = data.get("project_id")

        if not video_path or not os.path.exists(video_path):
            await websocket.send_json({"type": "error", "message": "Video file not found"})
            return
            
        if not project_id:
            await websocket.send_json({"type": "error", "message": "Project ID missing"})
            return

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            await websocket.send_json({"type": "error", "message": "Project not found"})
            return

        # Fetch existing segments and send them to the client immediately
        existing_segments = db.query(Segment).filter(Segment.project_id == project_id).order_by(Segment.start_time).all()
        resume_start = 0.0
        
        if existing_segments:
            print(f"Resuming {len(existing_segments)} existing segments for project {project_id}")
            for seg in existing_segments:
                await websocket.send_json({
                    "type": "segment",
                    "data": {
                        "id": seg.id,
                        "start": seg.start_time,
                        "end": seg.end_time,
                        "text": seg.text_original
                    }
                })
            resume_start = existing_segments[-1].end_time

        if project.status in ["reviewing", "translating", "translated", "dubbing", "finished"]:
            print(f"Project {project_id} already transcribed (status: {project.status})")
            await websocket.send_json({"type": "done"})
            return

        await websocket.send_json({"type": "status", "message": "Extracting audio..."})
        audio_path = extract_audio(video_path, start_time=resume_start)

        # Core transcription logic
        async def progress_callback(time_str):
            await websocket.send_json({
                "type": "progress",
                "message": f"Transcribing: {time_str}"
            })

        final_processed_subtitles = await transcription_service.transcribe(
            audio_path, resume_start, progress_callback=progress_callback
        )

        # 3. 统一保存并发送给前端
        for sub in final_processed_subtitles:
            sub_id = sub.get("id", str(uuid.uuid4()))
            new_db_segment = Segment(
                id=sub_id,
                project_id=project_id,
                start_time=sub["start"],
                end_time=sub["end"],
                text_original=sub["text"]
            )
            db.add(new_db_segment)
            db.commit()

            await websocket.send_json({
                "type": "segment",
                "data": {
                    "id": sub_id,
                    "start": sub["start"],
                    "end": sub["end"],
                    "text": sub["text"]
                }
            })

        # 录音提取完成，更新项目状态
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.status = "reviewing"
            db.commit()
            
        await websocket.send_json({"type": "done"})

    except Exception as e:
        import traceback
        traceback.print_exc()
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        db.close()
        # 显式卸载模型并清空显存
        
        try:
            await websocket.close()
        except:
            pass
