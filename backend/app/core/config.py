import os
from pydantic_settings import BaseSettings
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Vibe Video API"
    VERSION: str = "3.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
    BACKEND_DIR: Path = PROJECT_ROOT / "backend"
    BIN_DIR: Path = BACKEND_DIR / "bin"
    DATA_DIR: Path = BACKEND_DIR / "data"
    TEMP_DIR: Path = BACKEND_DIR / "temp"
    OUTPUT_DIR: Path = BACKEND_DIR / "data" / "output"
    AUDIO_DIR: Path = BACKEND_DIR / "data" / "audio"
    VIDEO_DIR: Path = BACKEND_DIR / "data" / "video"
    CACHE_DIR: Path = BACKEND_DIR / "data" / "cache"
    MODELS_DIR: Path = PROJECT_ROOT / "models"
    WHISPER_MODEL: str = "ggml-large-v3.bin"
    VAD_MODEL: str = "ggml-silero-v5.1.2.bin"
    
    # External Tools
    FFMPEG_PATH: Path = BIN_DIR / "ffmpeg.exe"
    
    # LLM Settings
    LLM_STRATEGY: str = "priority"
    LLM_MODEL: str = "gpt-3.5-turbo"
    
    # Database
    DATABASE_URL: str = f"sqlite:///{BACKEND_DIR}/db/vibe_video.db"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }

settings = Settings()

# Ensure directories exist
for path in [settings.DATA_DIR, settings.TEMP_DIR, settings.OUTPUT_DIR, settings.AUDIO_DIR, settings.VIDEO_DIR, settings.CACHE_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# Configure pydub
from pydub import AudioSegment
if settings.FFMPEG_PATH.exists():
    AudioSegment.converter = str(settings.FFMPEG_PATH)
    os.environ["PATH"] += os.pathsep + str(settings.BIN_DIR)
