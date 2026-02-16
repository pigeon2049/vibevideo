import yt_dlp
import os
from utils.file_manager import VIDEO_DIR, generate_temp_filename

def download_video(url: str) -> dict:
    """
    Downloads video from YouTube URL.
    Returns a dictionary with video info including path.
    """
    # Create a unique filename base
    filename_base = generate_temp_filename("").replace(".", "") 
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(VIDEO_DIR, f'{filename_base}.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        
        return {
            "title": info.get("title", "Unknown"),
            "duration": info.get("duration", 0),
            "path": os.path.abspath(filename),
            "thumbnail": info.get("thumbnail"),
            "original_url": url
        }

if __name__ == "__main__":
    # Test
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw" # Me at the zoo (short)
    try:
        result = download_video(url)
        print(f"Downloaded: {result}")
    except Exception as e:
        print(f"Error: {e}")
