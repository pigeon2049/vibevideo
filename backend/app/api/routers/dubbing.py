from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import json
import logging
from app.db.database import get_db
from app.services.manager import project_manager

logger = logging.getLogger("vibe-video.api.dubbing")
router = APIRouter(prefix="/dub", tags=["dubbing"])

class DubRequest(BaseModel):
    project_id: str
    voice: Optional[str] = None
    background_volume: float = 0.1

@router.post("")
async def dub_endpoint(request: DubRequest, db: Session = Depends(get_db)):
    try:
        # For dubbing, we wrap the project_manager.run_dubbing into a generator
        # if we want to provide granular progress updates like before.
        # Alternatively, we can just return the final result if it's fast enough or use a task queue.
        # For parity with original logic:
        
        async def dub_generator():
            try:
                # The manager now returns an async generator yielding dicts
                async for status_update in project_manager.run_dubbing(
                    db, request.project_id, request.voice, request.background_volume
                ):
                    yield json.dumps(status_update) + "\n"
            except Exception as e:
                logger.error(f"Dubbing Generator Error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                yield json.dumps({"step": "error", "message": str(e)}) + "\n"

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
        raise HTTPException(status_code=500, detail=str(e))
