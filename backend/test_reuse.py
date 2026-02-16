import os
import sys
import time

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services import downloader
from utils.file_manager import VIDEO_DIR

def test_reuse():
    url = "https://www.youtube.com/watch?v=Kdql4I-NJ0M"
    
    print("--- Test 1: First Download ---")
    start_time = time.time()
    result1 = downloader.download_video(url)
    duration1 = time.time() - start_time
    print(f"Result 1: {result1}")
    print(f"Time taken: {duration1:.2f}s")
    
    path1 = result1['path']
    if not os.path.exists(path1):
        print("FAIL: File does not exist after first download")
        return

    # Check if name is ID-based (should start with Kdql4I-NJ0M)
    video_id = "Kdql4I-NJ0M"
    if not os.path.basename(path1).startswith(video_id):
        print(f"FAIL: Filename {os.path.basename(path1)} does not start with ID {video_id}")
        return
    
    print("\n--- Test 2: Second Download (should reuse) ---")
    start_time = time.time()
    result2 = downloader.download_video(url)
    duration2 = time.time() - start_time
    print(f"Result 2: {result2}")
    print(f"Time taken: {duration2:.2f}s")
    
    if result2['path'] != path1:
        print("FAIL: Second download returned different path")
        return
    
    if duration2 > duration1 * 0.5: # Reuse should be significantly faster
        print(f"WARNING: Second 'download' took {duration2:.2f}s, which is not significantly faster than first ({duration1:.2f}s)")
    else:
        print(f"SUCCESS: Reuse was fast ({duration2:.2f}s vs {duration1:.2f}s)")

    if result2.get('download_format') == 'reused':
        print("SUCCESS: Result correctly flagged as 'reused'")
    else:
        print(f"FAIL: Result flag is {result2.get('download_format')}, expected 'reused'")

if __name__ == "__main__":
    test_reuse()
