from fastapi import APIRouter, WebSocket, Depends
import json
import logging
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.services.manager import project_manager
from app.services.transcription_service import transcription_service
from app.db.models import Segment, Project

logger = logging.getLogger("vibe-video.api.transcription")
router = APIRouter(prefix="/ws", tags=["transcription"])

@router.websocket("/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    await websocket.accept()
    # Note: We need a way to get the DB session for the websocket
    # Since Depends(get_db) doesn't work directly inside the websocket handler for long-lived sessions sometimes,
    # we'll use SessionLocal directly or handle it carefully.
    from app.db.database import SessionLocal
    db = SessionLocal()

    try:
        data = await websocket.receive_json()
        project_id = data.get("project_id")
        
        project = project_manager.get_project(db, project_id)
        if not project:
            await websocket.send_json({"type": "error", "message": "Project not found"})
            return

        # Handle existing segments
        if project.segments:
            for seg in project.segments:
                await websocket.send_json({
                    "type": "segment",
                    "data": {
                        "id": seg.id,
                        "start": seg.start_time,
                        "end": seg.end_time,
                        "text": seg.text_original
                    }
                })

        # Check if already transcribed
        if project.status not in ["idle", "transcribing"]:
            await websocket.send_json({"type": "done"})
            return

        await websocket.send_json({"type": "status", "message": "Extracting audio..."})
        # This will be handled by the manager
        segments = await project_manager.run_transcription(db, project_id)
        
        for s in segments:
            await websocket.send_json({
                "type": "segment",
                "data": s
            })
            
        await websocket.send_json({"type": "done"})

    except Exception as e:
        import traceback
        error_msg = f"WebSocket Error: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        await websocket.send_json({"type": "error", "message": error_msg})
    finally:
        db.close()
        try:
            await websocket.close()
        except:
            pass
