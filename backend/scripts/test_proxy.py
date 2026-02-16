import sys
import os

# Add parent directory to path to import utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.downloader import get_system_proxy

if __name__ == "__main__":
    print("Testing system proxy detection...")
    print("-" * 50)
    proxy = get_system_proxy()
    if proxy:
        print(f"\n[SUCCESS] Proxy detected and will be used: {proxy}")
    else:
        print("\n[INFO] No proxy detected - will connect directly")
    print("-" * 50)
