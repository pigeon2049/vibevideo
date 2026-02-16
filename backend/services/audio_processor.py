import os
import subprocess
import imageio_ffmpeg
from utils.file_manager import TEMP_DIR, OUTPUT_DIR, generate_temp_filename

def get_ffmpeg_cmd():
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except:
        return "ffmpeg" # Fallback to system

def isolate_audio(video_path: str) -> str:
    """
    Extracts audio from video.
    Returns path to audio file.
    """
    output_path = os.path.join(TEMP_DIR, generate_temp_filename("wav"))
    ffmpeg = get_ffmpeg_cmd()
    
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
        output_path
    ]
    
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def separate_vocals(audio_path: str) -> dict:
    """
    Separates vocals using Demucs.
    Returns dict with paths to 'vocals' and 'no_vocals' (background).
    """
    # Using Demucs CLI for simplicity
    # demucs -n htdemucs --two-stems=vocals -o <TEMP_DIR> <audio_path>
    model = "htdemucs"
    cmd = [
        "demucs", 
        "-n", model,
        "--two-stems=vocals",
        "-o", os.path.join(TEMP_DIR, "separated"),
        audio_path
    ]
    
    # This might take a while
    print(f"Running Demucs on {audio_path}...")
    subprocess.run(cmd, check=True)
    
    # Demucs output structure: <out_dir>/<model>/<filename>/vocals.wav
    filename = os.path.splitext(os.path.basename(audio_path))[0]
    base_dir = os.path.join(TEMP_DIR, "separated", model, filename)
    
    return {
        "vocals": os.path.join(base_dir, "vocals.wav"),
        "background": os.path.join(base_dir, "no_vocals.wav")
    }

def merge_audio_video(video_path: str, audio_path: str, output_path: str = None) -> str:
    """
    Merges video with new audio.
    """
    if not output_path:
        output_path = os.path.join(OUTPUT_DIR, generate_temp_filename("mp4"))
        
    ffmpeg = get_ffmpeg_cmd()
    
    # -c:v copy to copy video stream without re-encoding (fast)
    # -c:a aac to encode audio
    # -map 0:v:0 (video from first input)
    # -map 1:a:0 (audio from second input)
    # -shortest to stop when shortest stream ends
    
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_path
    ]
    
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

def mix_audio_tracks(background_path: str, speech_path: str, background_volume: float = 0.3) -> str:
    """
    Mixes background audio (at lower volume) with speech audio.
    """
    output_path = os.path.join(TEMP_DIR, generate_temp_filename("wav"))
    ffmpeg = get_ffmpeg_cmd()
    
    # ffmpeg -i bg.wav -i speech.wav -filter_complex "[0:a]volume=0.3[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=longest" out.wav
    
    filter_complex = f"[0:a]volume={background_volume}[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first"
    
    cmd = [
        ffmpeg, "-y",
        "-i", background_path,
        "-i", speech_path,
        "-filter_complex", filter_complex,
        output_path
    ]
    
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path
