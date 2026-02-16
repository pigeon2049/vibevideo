import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.downloader import download_video

if __name__ == "__main__":
    # Test with the problematic video
    url = "https://www.youtube.com/watch?v=Kdql4I-NJ0M"
    
    print("=" * 80)
    print(f"Testing download with URL: {url}")
    print("=" * 80)
    
    try:
        result = download_video(url)
        print("\n" + "=" * 80)
        print("SUCCESS!")
        print("=" * 80)
        print(f"Title: {result['title']}")
        print(f"Duration: {result['duration']}s")
        print(f"Path: {result['path']}")
        print(f"Format: {result['download_format']}")
        print("=" * 80)
    except Exception as e:
        print("\n" + "=" * 80)
        print("FAILED!")
        print("=" * 80)
        print(f"Error: {e}")
        print("=" * 80)
