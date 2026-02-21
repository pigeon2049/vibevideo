import os
import torch
import threading
import subprocess
from pathlib import Path
from fastapi import APIRouter, WebSocket
from faster_whisper import WhisperModel
import uuid
import re
from db.database import SessionLocal
from db.models import Segment, Project

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
# 模型单例
# ==================================================
_model = None
_lock = threading.Lock()

def get_model():
    global _model
    with _lock:
        if _model is None:
            if not MODEL_DIR.exists():
                raise RuntimeError(f"Model directory not found: {MODEL_DIR}")

            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"

            print(f"🚀 Loading Whisper from: {MODEL_DIR}")
            _model = WhisperModel(
                str(MODEL_DIR),
                device=device,
                compute_type=compute_type
            )
            print("✅ Whisper model loaded successfully")
    return _model

# ==================================================
# 音频提取
# ==================================================
def extract_audio(video_path: str) -> str:
    output_path = TEMP_DIR / (Path(video_path).stem + ".wav")
    if not FFMPEG_PATH.exists():
        raise RuntimeError(f"ffmpeg not found: {FFMPEG_PATH}")

    command = [
        str(FFMPEG_PATH), "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(output_path)
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(output_path)

# ==================================================
# ✨ 优化后的断句引擎
# ==================================================
class SubtitleSplitter:
    """
    负责将 Whisper 的原始 Segment 进一步规范化。
    如果单句过长（超过 max_chars），尝试根据标点符号拆分。
    """
    def __init__(self, max_chars=25):
        self.max_chars = max_chars
        # 用于拆分长句的正则（匹配中英文常见停顿标点）
        self.split_patterns = r"[,，。！？!?；;]"

    def split_text(self, segment_dict):
        text = segment_dict["text"].strip()
        start = segment_dict["start"]
        end = segment_dict["end"]
        
        # 如果长度在理想范围内，直接返回
        if len(text) <= self.max_chars:
            return [segment_dict]

        # 尝试根据标点符号切分长句
        parts = re.split(f"({self.split_patterns})", text)
        results = []
        current_chunk = ""
        
        # 粗略分配时间戳（等比分配）
        char_duration = (end - start) / len(text) if len(text) > 0 else 0
        current_start = start

        for i in range(0, len(parts)-1, 2):
            chunk = parts[i] + (parts[i+1] if i+1 < len(parts) else "")
            if not chunk.strip(): continue
            
            chunk_len = len(chunk)
            chunk_end = current_start + (chunk_len * char_duration)
            
            results.append({
                "id": str(uuid.uuid4()),
                "start": round(current_start, 3),
                "end": round(min(chunk_end, end), 3),
                "text": chunk.strip()
            })
            current_start = chunk_end

        return results if results else [segment_dict]

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

        model = get_model()
        splitter = SubtitleSplitter(max_chars=22) # 建议中文每行 22 字左右视觉体验最好

        await websocket.send_json({"type": "status", "message": "Extracting audio..."})
        audio_path = extract_audio(video_path)

        await websocket.send_json({"type": "status", "message": "Transcribing..."})

        # VAD 参数调优：减小 min_silence_duration 使其对停顿更灵敏
        segments, _ = model.transcribe(
            audio_path,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400) 
        )

        for segment in segments:
            if not segment.text.strip():
                continue

            raw_data = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip()
            }

            # 处理断句（过长则拆分，不长则原样返回）
            processed_subtitles = splitter.split_text(raw_data)

            for sub in processed_subtitles:
                sub_id = sub.get("id", str(uuid.uuid4()))
                
                # 持久化到数据库
                new_db_segment = Segment(
                    id=sub_id,
                    project_id=project_id,
                    start_time=sub["start"],
                    end_time=sub["end"],
                    text_original=sub["text"]
                )
                db.add(new_db_segment)
                db.commit()

                # 统一发送格式：既能用于 UI 显示，也能用于翻译
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
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        db.close()
        await websocket.close()