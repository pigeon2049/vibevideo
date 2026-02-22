from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json
from app.db.database import get_db
from app.services.manager import project_manager

router = APIRouter(prefix="/translate", tags=["translation"])

class TranslateRequest(BaseModel):
    project_id: str
    target_language: str
    context: Optional[List[str]] = []

@router.post("-stream")
async def translate_stream_endpoint(request: TranslateRequest, db: Session = Depends(get_db)):
    try:
        async def event_generator():
            async for chunk in project_manager.run_translation(db, request.project_id, request.target_language):
                yield json.dumps(chunk, ensure_ascii=False) + "\n"

        return StreamingResponse(
            event_generator(), 
            media_type="application/x-ndjson"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
