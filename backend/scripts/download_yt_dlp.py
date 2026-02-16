import os
import requests
import shutil

def download_yt_dlp():
    url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    bin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
    os.makedirs(bin_dir, exist_ok=True)
    target_path = os.path.join(bin_dir, "yt-dlp.exe")
    
    print(f"Downloading latest yt-dlp.exe from {url}...")
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"Successfully downloaded to: {target_path}")
        return target_path
    except Exception as e:
        print(f"Error downloading yt-dlp.exe: {e}")
        return None

if __name__ == "__main__":
    download_yt_dlp()
