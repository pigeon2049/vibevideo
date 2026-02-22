import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Explicit imports to avoid any package/module ambiguity
from app.api.routers.projects import router as projects_router
from app.api.routers.transcription import router as transcription_router
from app.api.routers.translation import router as translation_router
from app.api.routers.dubbing import router as dubbing_router

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.db.database import engine, Base

# Setup logging
setup_logging()

# Force ProactorEventLoop on Windows for subprocess support
import sys
import asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    print("[INIT] Windows ProactorEventLoopPolicy enforced", flush=True)

# Initialize Database
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers under the /api/v1 prefix
app.include_router(projects_router, prefix=settings.API_V1_STR)
app.include_router(transcription_router, prefix=settings.API_V1_STR)
app.include_router(translation_router, prefix=settings.API_V1_STR)
app.include_router(dubbing_router, prefix=settings.API_V1_STR)

# Static Files
app.mount("/output", StaticFiles(directory=str(settings.OUTPUT_DIR)), name="output")
app.mount("/temp", StaticFiles(directory=str(settings.TEMP_DIR)), name="temp")
app.mount("/audio", StaticFiles(directory=str(settings.AUDIO_DIR)), name="audio")

@app.get("/")
async def root():
    return {
        "status": "online", 
        "message": f"Welcome to {settings.PROJECT_NAME} v{settings.VERSION}",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    # Important: run this as app.main:app
    # loop="asyncio" + policy setup in backend/app/main.py ensures windows subprocess support
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, loop="asyncio")
