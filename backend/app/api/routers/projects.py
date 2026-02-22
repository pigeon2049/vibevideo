import uuid
import os
import shutil
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db.database import get_db
from app.services.manager import project_manager
from app.services.downloader_service import downloader_service
from app.core.config import settings
from app.db.models import Segment

router = APIRouter(prefix="/projects", tags=["projects"])

class DownloadRequest(BaseModel):
    url: str
    cookies: Optional[str] = None

# --- SPECIFIC ROUTES FIRST ---

@router.post("/download")
async def download_video(request: DownloadRequest, db: Session = Depends(get_db)):
    try:
        info = await downloader_service.download(request.url, request.cookies)
        project = project_manager.create_project(db, info["path"])
        return {
            "project_id": project.id,
            "title": info["title"],
            "path": info["path"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload")
async def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        file_path = settings.VIDEO_DIR / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        project = project_manager.create_project(db, str(file_path))
        return {
            "project_id": project.id,
            "path": str(file_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- PARAMETERIZED ROUTES LATER ---

@router.get("/{project_id}")
async def get_project(project_id: str, db: Session = Depends(get_db)):
    project = project_manager.get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return {
        "id": project.id,
        "video_path": str(project.video_path),
        "status": project.status,
        "target_language": project.target_language,
        "final_video_url": project.final_video_url,
        "segments": [
            {
                "id": s.id,
                "start": s.start_time,
                "end": s.end_time,
                "text": s.text_original,
                "text_translated": s.text_translated,
            }
            for s in project.segments
        ]
    }

@router.post("/{project_id}/segment/{segment_id}/reset")
async def reset_segment(project_id: str, segment_id: str, mode: str = "single", db: Session = Depends(get_db)):
    if mode == "single":
        seg = db.query(Segment).filter(Segment.id == segment_id).first()
        if seg:
            seg.text_translated = None
            db.commit()
    else:
        # Reset all after
        seg = db.query(Segment).filter(Segment.id == segment_id).first()
        if seg:
            after = db.query(Segment).filter(
                Segment.project_id == project_id,
                Segment.start_time >= seg.start_time
            ).all()
            for s in after:
                s.text_translated = None
            db.commit()
    return {"status": "ok"}

@router.put("/{project_id}/segment/{segment_id}/translation")
async def update_translation(project_id: str, segment_id: str, data: dict, db: Session = Depends(get_db)):
    seg = db.query(Segment).filter(Segment.id == segment_id).first()
    if seg:
        seg.text_translated = data.get("text_translated")
        db.commit()
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Segment not found")
