import os
import shutil
import uuid

TEMP_DIR = "temp"
VIDEO_DIR = os.path.join(TEMP_DIR, "videos")
AUDIO_DIR = os.path.join(TEMP_DIR, "audio")
OUTPUT_DIR = os.path.join(TEMP_DIR, "output")

def init_dirs():
    os.makedirs(VIDEO_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_video_path(filename: str) -> str:
    return os.path.join(VIDEO_DIR, filename)

def generate_temp_filename(ext: str = "mp4") -> str:
    return f"{uuid.uuid4()}.{ext}"

def cleanup_temp():
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        init_dirs()

# Initialize on import (or call explicitly)
init_dirs()
