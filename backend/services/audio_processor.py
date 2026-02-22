import os
import subprocess
import imageio_ffmpeg
from utils.file_manager import TEMP_DIR, OUTPUT_DIR, generate_temp_filename

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(BACKEND_DIR, "bin")

if os.path.isdir(BIN_DIR) and BIN_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")

def get_ffmpeg_cmd():
    # Attempt to use specific bin/ffmpeg.exe if it exists
    local_ffmpeg = os.path.join(BIN_DIR, "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
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

def merge_audio_video(video_path: str, background_audio: str, tts_segments: list, bg_volume: float = 0.1, subtitle_path: str = None) -> str:
    """
    Merges video with mixed background audio and TTS segments.
    Optionally burns subtitles into the video if subtitle_path is provided.
    """
    from pydub import AudioSegment
    import math
    
    ffmpeg_exe = get_ffmpeg_cmd()
    
    # Let pydub configure itself. We also tell it explicitly where ffmpeg and ffprobe are if we can.
    AudioSegment.converter = ffmpeg_exe
    
    # Try finding ffprobe in the same dir as the converter
    ffprobe_exe = os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe.exe" if os.name == "nt" else "ffprobe")
    if os.path.exists(ffprobe_exe):
        AudioSegment.ffprobe = ffprobe_exe
    
    print("Loading background audio for mixing...")
    bg_track = AudioSegment.from_file(background_audio)
    
    if bg_volume < 1.0:
        db_change = 20 * math.log10(max(bg_volume, 0.001))
        bg_track = bg_track + db_change
        
    print(f"Mixing {len(tts_segments)} TTS segments...")
    for seg in tts_segments:
        audio_file = seg.get("audio_file")
        if audio_file and os.path.exists(audio_file):
            try:
                tts_track = AudioSegment.from_file(audio_file)
                pos_ms = int(seg.get("start", 0) * 1000)
                bg_track = bg_track.overlay(tts_track, position=pos_ms)
            except Exception as e:
                print(f"Failed to overlay segment {seg.get('id', 'unknown')}: {e}")
                
    mixed_audio_path = os.path.join(TEMP_DIR, generate_temp_filename("wav"))
    print("Exporting mixed audio track...")
    bg_track.export(mixed_audio_path, format="wav")
    
    output_path = os.path.join(OUTPUT_DIR, generate_temp_filename("mp4"))
    
    cmd = [
        ffmpeg_exe, "-y",
        "-i", video_path,
        "-i", mixed_audio_path
    ]

    if subtitle_path and os.path.exists(subtitle_path):
        # Escape the subtitle path for Windows
        # ffmpeg requires paths in filters to be escaped, e.g., C:/path/to/file.srt -> C\:/path/to/file.srt
        # But using forward slashes generally works and is less error-prone.
        escaped_sub_path = subtitle_path.replace('\\', '/')
        # Windows drive letter escaping (C:/ -> C\:/)
        if len(escaped_sub_path) > 1 and escaped_sub_path[1] == ':':
            escaped_sub_path = escaped_sub_path[0] + '\\:' + escaped_sub_path[2:]
            
        print(f"Adding subtitles filter with path: {escaped_sub_path}")
        cmd.extend(["-vf", f"subtitles='{escaped_sub_path}'"])
    else:
        cmd.extend(["-c:v", "copy"])

    cmd.extend([
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_path
    ])
    
    print("Running ffmpeg to merge video and audio...")
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
