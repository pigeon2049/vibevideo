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

def format_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp format HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int(round((seconds - int(seconds)) * 1000))
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

def generate_srt(segments: list, output_filename: str = None) -> str:
    """
    Generate an SRT file from a list of segments.
    Each segment should be a dictionary with 'start', 'end', and 'text' keys.
    """
    if not output_filename:
        output_filename = os.path.join(OUTPUT_DIR, generate_temp_filename("srt"))
        
    with open(output_filename, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(segments, start=1):
            start = format_timestamp(segment['start'])
            end = format_timestamp(segment['end'])
            text = segment['text'].strip()
            
            f.write(f"{i}\n")
            f.write(f"{start} --> {end}\n")
            f.write(f"{text}\n\n")
            
    return output_filename
