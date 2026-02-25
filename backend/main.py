import os
import shutil
import uuid
import json
import asyncio
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import sys
import asyncio

# Force ProactorEventLoop on Windows for subprocess support
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 1. 环境初始化
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

# 2. 业务组件导入
from app.services.downloader_service import downloader_service as downloader
from app.services.translation_service import translation_service as translator
from app.services.tts_service import tts_service as tts
from app.services.audio_service import audio_service as audio_processor
from app.api.routers.transcription import router as transcriber_router
from app.utils.file_manager import TEMP_DIR, OUTPUT_DIR, VIDEO_DIR
from app.db.database import engine, Base, get_db
from app.db.models import Project, Segment

# 自动创建所有表
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Vibe Video API - Full Async Version")

# ==================================================
# 中间件配置 (必须置于路由注册之前)
# ==================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载业务路由
app.include_router(transcriber_router)

# 静态目录挂载 (用于访问生成的音视频)
app.mount("/output", StaticFiles(directory=OUTPUT_DIR), name="output")
app.mount("/temp", StaticFiles(directory=TEMP_DIR), name="temp")


# ==================================================
# 全局状态管理
# ==================================================
active_translation_streams = {} # project_id -> stream_id

# ==================================================
# 数据模型定义
# ==================================================

class DownloadRequest(BaseModel):
    url: str
    cookies: Optional[str] = None

class SegmentModel(BaseModel):
    id: str
    start: float
    end: float
    text: str
    audio_file: Optional[str] = None

class TranslateRequest(BaseModel):
    project_id: str
    target_language: str
    context: Optional[List[str]] = []

class UpdateTranslationRequest(BaseModel):
    text_translated: str

class DubRequest(BaseModel):
    project_id: str
    voice: Optional[str] = None
    background_volume: float = 0.1

# ==================================================
# API 端点
# ==================================================

@app.get("/")
async def root():
    return {"status": "online", "service": "Vibe Video API", "version": "2.5.0"}

# --- 获取项目状态 ---
@app.get("/project/{project_id}")
async def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 格式化 segments 返回
    segments = [
        {
            "id": s.id,
            "start": s.start_time,
            "end": s.end_time,
            "text": s.text_original,
            "text_translated": s.text_translated,
        }
        for s in project.segments
    ]
    return {
        "id": project.id,
        "video_path": project.video_path,
        "status": project.status,
        "target_language": project.target_language,
        "final_video_url": project.final_video_url,
        "segments": segments
    }

# --- 视频下载 ---
@app.post("/download")
async def download_video_endpoint(request: DownloadRequest, db: Session = Depends(get_db)):
    try:
        print(f"📥 Received download task: {request.url}")
        # 该操作通常涉及长时间 IO，建议确保 downloader 内部无阻塞或运行在执行器中
        result = await downloader.download(request.url, request.cookies)
        
        # 检查是否已存在具有相同 video_path 的项目
        existing_project = db.query(Project).filter(Project.video_path == result.get("path")).first()
        if existing_project:
            print(f"🔄 Resuming existing project: {existing_project.id}")
            result["project_id"] = existing_project.id
            return result

        # 创建数据库记录
        new_project = Project(
            video_path=result.get("path"),
            status="transcribing"
        )
        db.add(new_project)
        db.commit()
        db.refresh(new_project)
        
        result["project_id"] = new_project.id
        return result
    except Exception as e:
        print(f"❌ Download Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 本地上传 ---
@app.post("/upload")
async def upload_video_endpoint(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        ext = os.path.splitext(file.filename)[1]
        filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(VIDEO_DIR, filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 创建数据库记录
        new_project = Project(
            video_path=file_path,
            status="transcribing"
        )
        db.add(new_project)
        db.commit()
        db.refresh(new_project)
        
        return {"title": file.filename, "path": file_path, "project_id": new_project.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 流式翻译 (解决 Pending 核心) ---
@app.post("/translate-stream")
async def translate_stream_endpoint(request: TranslateRequest, db: Session = Depends(get_db)):
    """
    接收翻译请求，通过 NDJSON 流式返回结果。
    内部读取数据库中未翻译的片段。
    """
    print(f"📡 API HIT: /translate-stream | Project: {request.project_id}")
    
    stream_id = str(uuid.uuid4())
    active_translation_streams[request.project_id] = stream_id
    
    try:
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        # 提取未翻译的片段，每次最多处理 20 个（可配置）
        segments_to_translate = db.query(Segment).filter(
            Segment.project_id == request.project_id,
            (Segment.text_translated == None) | (Segment.text_translated == "")
        ).order_by(Segment.start_time).limit(20).all()
        
        if not segments_to_translate:
            return StreamingResponse(iter([])) # 返回空流
            
        # 构建 segments_data 供翻译服务使用
        segments_data = [
            {"id": s.id, "start": s.start_time, "end": s.end_time, "text": s.text_original}
            for s in segments_to_translate
        ]
        
        # 更新项目状态
        project.status = "translating"
        project.target_language = request.target_language
        db.commit()
        
        async def event_generator():
            # 需要在生成器内新建 DB Session，因为 FastAPI 的 Depends 在生成器中可能失效
            # 或者传递已有的 DB 并在每次 yield 前 commit
            from db.database import SessionLocal
            stream_db = SessionLocal()
            try:
                loop = asyncio.get_event_loop()
                
                gen = translator.translate_segments_stream(
                    segments=segments_data,
                    target_language=request.target_language,
                    history_context=request.context or []
                )

                def get_next_chunk():
                    try:
                        return next(gen)
                    except StopIteration:
                        return None

                while True:
                    if active_translation_streams.get(request.project_id) != stream_id:
                        print(f"🛑 Stream cancelled for project {request.project_id} (before chunk)")
                        break
                        
                    chunk = await loop.run_in_executor(None, get_next_chunk)
                    
                    if active_translation_streams.get(request.project_id) != stream_id:
                        print(f"🛑 Stream cancelled for project {request.project_id} (after chunk)")
                        break
                    
                    if chunk is None:
                        break
                        
                    # 及时更新数据库中的翻译结果
                    for translated_seg in chunk:
                        db_segment = stream_db.query(Segment).filter(Segment.id == translated_seg["id"]).first()
                        if db_segment and "text" in translated_seg:
                            db_segment.text_translated = translated_seg["text"]
                            db_segment.tts_audio_path = None
                    stream_db.commit()
                        
                    yield json.dumps(chunk, ensure_ascii=False) + "\n"
                    await asyncio.sleep(0.01)
                    
                # 检查是否全部已翻译
                untranslated_count = stream_db.query(Segment).filter(
                    Segment.project_id == request.project_id,
                    Segment.text_translated == None
                ).count()
                
                if untranslated_count == 0:
                    proj = stream_db.query(Project).filter(Project.id == request.project_id).first()
                    if proj:
                        proj.status = "translated"
                        stream_db.commit()

            finally:
                stream_db.close()

        return StreamingResponse(
            event_generator(), 
            media_type="application/x-ndjson",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        print(f"❌ Endpoint Fatal Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# --- 重置片段翻译 ---
@app.post("/project/{project_id}/segment/{segment_id}/reset")
async def reset_segment_translation(project_id: str, segment_id: str, mode: str = "single", db: Session = Depends(get_db)):
    segment = db.query(Segment).filter(Segment.project_id == project_id, Segment.id == segment_id).first()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
        
    start_time = segment.start_time
    
    if mode == "all_after":
        # Reset this segment and all subsequent segments
        segments_to_reset = db.query(Segment).filter(
            Segment.project_id == project_id,
            Segment.start_time >= start_time
        ).all()
        for s in segments_to_reset:
            s.text_translated = None
            s.tts_audio_path = None
    else:
        # Reset just this one
        segment.text_translated = None
        segment.tts_audio_path = None
    
    # 确保项目的状态允许重新翻译
    project = db.query(Project).filter(Project.id == project_id).first()
    if project and project.status in ["translated", "finished", "dubbing"]:
        project.status = "reviewing"
        
    db.commit()
    return {"status": "success"}

# --- 更新片段翻译 ---
@app.put("/project/{project_id}/segment/{segment_id}/translation")
async def update_segment_translation(
    project_id: str, 
    segment_id: str, 
    request: UpdateTranslationRequest, 
    db: Session = Depends(get_db)
):
    segment = db.query(Segment).filter(Segment.project_id == project_id, Segment.id == segment_id).first()
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")
        
    segment.text_translated = request.text_translated
    segment.tts_audio_path = None
    db.commit()
    return {"status": "success", "id": segment.id, "text_translated": segment.text_translated}

# --- 配音合成 ---
@app.post("/dub")
async def dub_endpoint(request: DubRequest, db: Session = Depends(get_db)):
    print(f"📡 API HIT: /dub | Project: {request.project_id}")
    try:
        project = db.query(Project).filter(Project.id == request.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        project.status = "dubbing"
        db.commit()
        
        # 获取所有片段（并转换为原来的字典格式以适应 tts）
        all_segments = project.segments
        segments_dict = [
            {
                "id": s.id,
                "start": s.start_time,
                "end": s.end_time,
                "text": s.text_translated or s.text_original
            }
            for s in all_segments if s.text_translated
        ]
        
        segments_dict.sort(key=lambda x: x["start"])
        paragraphs = []
        if segments_dict:
            current_para = {
                "id": f"para_{segments_dict[0]['id']}", 
                "start": segments_dict[0]["start"], 
                "end": segments_dict[0]["end"], 
                "texts": [segments_dict[0]["text"]],
                "segment_ids": [segments_dict[0]["id"]]
            }
            for i in range(1, len(segments_dict)):
                seg = segments_dict[i]
                gap = seg["start"] - current_para["end"]
                
                last_text = current_para["texts"][-1].strip()
                ends_with_sentence_break = False
                if last_text and last_text[-1] in ".。!?！？\n":
                    ends_with_sentence_break = True
                    
                if gap <= 1.0 and not ends_with_sentence_break:
                    current_para["texts"].append(seg["text"])
                    current_para["end"] = seg["end"]
                    current_para["segment_ids"].append(seg["id"])
                else:
                    paragraphs.append(current_para)
                    current_para = {
                        "id": f"para_{seg['id']}", 
                        "start": seg["start"], 
                        "end": seg["end"], 
                        "texts": [seg["text"]],
                        "segment_ids": [seg["id"]]
                    }
            paragraphs.append(current_para)

        for p in paragraphs:
            p["text"] = " ".join(p["texts"])
        
        async def dub_generator():
            import hashlib
            from utils.file_manager import AUDIO_DIR
            from db.database import SessionLocal
            stream_db = SessionLocal()
            try:
                loop = asyncio.get_event_loop()
                
                print(f"🎬 Step 1: Starting TTS for {len(paragraphs)} paragraphs (grouped from {len(segments_dict)} segments)...")
                initial_paras = [{"id": p["id"], "text": p["text"], "start": p["start"]} for p in paragraphs]
                yield json.dumps({"step": "tts", "current": 0, "total": len(paragraphs), "paragraphs": initial_paras}) + "\n"
                
                paragraphs_with_audio = []
                for i, para in enumerate(paragraphs):
                    text = para["text"]
                    if text.strip():
                        # Handle default voice selection
                        voice = request.voice
                        proj_lang = project.target_language or "zh"
                        print(f"[DEBUG] Dubbing: Requested voice: '{voice}', Project language: '{proj_lang}'")
                        if not voice or (isinstance(voice, str) and voice.lower() == "default"):
                            if proj_lang == "zh":
                                voice = tts.default_voice_zh
                            else:
                                voice = tts.default_voice_en
                            print(f"[DEBUG] Dubbing: Using default voice '{voice}' for language '{proj_lang}'")
                        else:
                            print(f"[DEBUG] Dubbing: Using requested voice '{voice}'")

                        text_hash = hashlib.md5(f"{text}_{voice}".encode()).hexdigest()
                        audio_path = os.path.join(AUDIO_DIR, f"tts_{text_hash}.mp3")
                        
                        if os.path.exists(audio_path):
                            print(f"⏩ Skipping TTS for paragraph {para['id']}, already exists")
                        else:
                            audio_path = await tts.generate_speech(text, voice, output_file=audio_path)
                            
                        for seg_id in para["segment_ids"]:
                            db_seg = stream_db.query(Segment).filter(Segment.id == seg_id).first()
                            if db_seg:
                                db_seg.tts_audio_path = audio_path
                        stream_db.commit()
                                
                        para["audio_file"] = audio_path
                    else:
                        para["audio_file"] = None
                        
                    paragraphs_with_audio.append(para)
                    audio_url = f"/{para['audio_file'].replace(os.sep, '/')}" if para["audio_file"] else None
                    para_info = {"id": para["id"], "text": para["text"], "start": para["start"], "audio_url": audio_url}
                    yield json.dumps({"step": "tts", "current": i + 1, "total": len(paragraphs), "paragraph": para_info}) + "\n"
                
                print("🔍 Step 2: Isolating and separating audio layers...")
                yield json.dumps({"step": "isolate"}) + "\n"
                original_audio = await audio_processor.isolate_audio(project.video_path)
                
                yield json.dumps({"step": "separate"}) + "\n"
                separated = await audio_processor.separate_vocals(original_audio)
                
                print("🛠 Step 3: Merging final high-fidelity video...")
                yield json.dumps({"step": "merge"}) + "\n"
                
                # Generate subtitle file
                from utils.file_manager import generate_srt
                srt_path = await loop.run_in_executor(None, generate_srt, segments_dict)
                print(f"📄 Subtitle file generated at: {srt_path}")
                
                # FIX: merge_audio_video is an async function, should be awaited directly,
                # NOT run in an executor (which would just return the coroutine object).
                temp_final_video_path = await audio_processor.merge_audio_video(
                    video_path=project.video_path,
                    background_audio=separated["background"],
                    tts_segments=paragraphs_with_audio,
                    bg_volume=request.background_volume,
                    subtitle_path=srt_path
                )
                
                # Rename to deterministic path
                final_filename = f"{request.project_id}.mp4"
                deterministic_path = os.path.join(OUTPUT_DIR, final_filename)
                if os.path.exists(deterministic_path):
                    try:
                        os.remove(deterministic_path)
                    except Exception:
                        pass
                shutil.move(temp_final_video_path, deterministic_path)
                
                proj = stream_db.query(Project).filter(Project.id == request.project_id).first()
                if proj:
                    proj.status = "finished"
                    proj.final_video_url = f"/output/{final_filename}"
                    stream_db.commit()
                
                yield json.dumps({
                    "step": "done",
                    "video_path": deterministic_path,
                    "url": f"/output/{final_filename}"
                }) + "\n"
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield json.dumps({"step": "error", "message": str(e)}) + "\n"
            finally:
                stream_db.close()
                
        return StreamingResponse(
            dub_generator(),
            media_type="application/x-ndjson",
            headers={
                "X-Accel-Buffering": "no",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# ==================================================
# 启动入口
# ==================================================

if __name__ == "__main__":
    # 自动初始化工作目录
    for d in [TEMP_DIR, OUTPUT_DIR, VIDEO_DIR]:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        
    print("🔥 Vibe Video Backend is firing up on http://localhost:8000")
    # loop="asyncio" + policy setup above ensures windows subprocess support
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=False, 
        loop="asyncio"
    )
