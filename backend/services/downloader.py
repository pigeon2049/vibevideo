import os
import sys
import tempfile
import subprocess
import json
import urllib.request
from utils.file_manager import VIDEO_DIR, generate_temp_filename

# Detect system proxy on Windows
if sys.platform == 'win32':
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None

# Path to the standalone yt-dlp executable and Deno runtime
BIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
YT_DLP_EXE = os.path.join(BIN_DIR, "yt-dlp.exe")
DENO_EXE = os.path.join(BIN_DIR, "deno.exe")

class MyLogger:
    def debug(self, msg):
        if msg.startswith('[debug] '):
            pass
        else:
            self.info(msg)

    def info(self, msg):
        print(f"INFO: {msg}")

    def warning(self, msg):
        print(f"WARNING: {msg}")

    def error(self, msg):
        print(f"ERROR: {msg}")

def get_system_proxy():
    """
    Detect system proxy settings on Windows.
    Returns proxy URL (e.g., 'http://127.0.0.1:7890') or None.
    """
    try:
        # Try to get proxy from urllib (which reads system settings)
        proxies = urllib.request.getproxies()
        if proxies:
            # Check for http or https proxy
            proxy = proxies.get('http') or proxies.get('https')
            if proxy:
                print(f"Detected system proxy: {proxy}")
                return proxy
        
        # On Windows, also try reading from registry directly
        if sys.platform == 'win32' and winreg:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                   r'Software\Microsoft\Windows\CurrentVersion\Internet Settings') as key:
                    proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')
                    if proxy_enable:
                        proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
                        if proxy_server:
                            # Add http:// prefix if not present
                            if not proxy_server.startswith('http'):
                                proxy_server = f'http://{proxy_server}'
                            print(f"Detected Windows registry proxy: {proxy_server}")
                            return proxy_server
            except (OSError, FileNotFoundError):
                pass
    except Exception as e:
        print(f"Error detecting proxy: {e}")
    
    print("No system proxy detected")
    return None

def download_video(url: str, cookies: str = None) -> dict:
    """
    Downloads video from YouTube URL using standalone yt-dlp.exe.
    Returns a dictionary with video info including path.
    Uses auto format selection first, then smart fallback.
    """
    if not os.path.exists(YT_DLP_EXE):
        raise FileNotFoundError(f"yt-dlp.exe not found at {YT_DLP_EXE}. Please run the download script first.")

    # Fetch video info first to get ID and check for existing file
    info_cmd = [YT_DLP_EXE, url, '--dump-json', '--no-playlist', '--no-check-certificates']
    system_proxy = get_system_proxy()
    if system_proxy:
        info_cmd.extend(['--proxy', system_proxy])
    
    # Also need cookies for info if video is restricted
    temp_cookie_for_info = None
    if cookies:
        try:
            fd, temp_cookie_for_info = tempfile.mkstemp(suffix=".txt", prefix="info_cookies_")
            with os.fdopen(fd, 'w') as f:
                f.write(cookies)
            info_cmd.extend(['--cookies', temp_cookie_for_info])
        except Exception as e:
            print(f"Error creating info cookie file: {e}")

    try:
        print(f"Fetching video info for: {url}")
        info_process = subprocess.Popen(
            info_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        info_stdout, info_stderr = info_process.communicate()
        
        if info_process.returncode == 0:
            video_info = json.loads(info_stdout)
            video_id = video_info.get('id')
            title = video_info.get('title', 'Unknown')
            
            # Check for existing file with this ID
            if video_id:
                for f in os.listdir(VIDEO_DIR):
                    if f.startswith(f"{video_id}."):
                        existing_path = os.path.join(VIDEO_DIR, f)
                        print(f"INFO: Found existing download: {existing_path}")
                        return {
                            "title": title,
                            "duration": video_info.get("duration", 0),
                            "path": os.path.abspath(existing_path),
                            "thumbnail": video_info.get("thumbnail"),
                            "original_url": url,
                            "download_format": "reused"
                        }
                outtmpl = os.path.join(VIDEO_DIR, f'%(id)s.%(ext)s')
            else:
                # Fallback to random filename if no ID found
                filename_base = generate_temp_filename("").replace(".", "") 
                outtmpl = os.path.join(VIDEO_DIR, f'{filename_base}.%(ext)s')
        else:
            print(f"Warning: Could not fetch video info: {info_stderr}")
            filename_base = generate_temp_filename("").replace(".", "") 
            outtmpl = os.path.join(VIDEO_DIR, f'{filename_base}.%(ext)s')
    except Exception as e:
        print(f"Error checking for existing download: {e}")
        filename_base = generate_temp_filename("").replace(".", "") 
        outtmpl = os.path.join(VIDEO_DIR, f'{filename_base}.%(ext)s')
    finally:
        if temp_cookie_for_info and os.path.exists(temp_cookie_for_info):
            try: os.remove(temp_cookie_for_info)
            except: pass

    # Strategy:
    # 1. First try without format specification - let yt-dlp choose the best
    # 2. If that fails, list available formats and pick intelligently (excluding images)
    
    cookie_file = None
    if cookies:
        try:
            fd, cookie_file = tempfile.mkstemp(suffix=".txt", prefix="cookies_")
            with os.fdopen(fd, 'w') as f:
                f.write(cookies)
            print(f"Using provided cookies via temp file: {cookie_file}")
        except Exception as e:
            print(f"Error creating cookie file: {e}")
            cookie_file = None
    
    def build_base_cmd(format_spec=None, player_client=None):
        """Build base yt-dlp command with optional format and player client"""
        cmd = [
            YT_DLP_EXE,
            url,
            '--output', outtmpl,
            '--no-playlist',
            '--print-json',
            '--no-check-certificates',
            '--ffmpeg-location', BIN_DIR,
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        ]
        
        # Add Deno runtime for JavaScript challenge solving (n-parameter)
        if os.path.exists(DENO_EXE):
            cmd.extend(['--js-runtimes', f'deno:{DENO_EXE}'])
        
        if format_spec:
            cmd.extend(['--format', format_spec])
        
        # Detect and use system proxy
        system_proxy = get_system_proxy()
        if system_proxy:
            cmd.extend(['--proxy', system_proxy])
        
        # Handle cookies and player client selection
        if cookie_file:
            cmd.extend(['--cookies', cookie_file])
            
            # Use specified player client or default to android_creator
            # android_creator bypasses n-parameter challenge and supports cookies
            if player_client:
                cmd.extend(['--extractor-args', f'youtube:player_client={player_client}'])
            else:
                # Default: try android_creator which works with cookies and avoids n-challenge
                cmd.extend(['--extractor-args', 'youtube:player_client=android_creator'])
        
        return cmd
    
    def try_download(cmd, description):
        """Helper to attempt download with given command"""
        try:
            print(f"Attempting download: {description}")
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                info = json.loads(stdout)
                filename = info.get('_filename')
                
                if not os.path.exists(filename):
                    base = os.path.basename(filename).split('.')[0]
                    for f in os.listdir(VIDEO_DIR):
                        if f.startswith(base):
                            filename = os.path.join(VIDEO_DIR, f)
                            break
                
                try:
                    print(f"INFO: Successfully downloaded: {description}")
                except UnicodeEncodeError:
                    print(f"INFO: Successfully downloaded: (description contains unencodable characters)")
                return {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration", 0),
                    "path": os.path.abspath(filename),
                    "thumbnail": info.get("thumbnail"),
                    "original_url": url,
                    "download_format": description
                }, None
            else:
                return None, stderr
        except Exception as e:
            return None, str(e)
    
    last_error = ""
    try:
        # ATTEMPT 1: Try with cookies using different player clients to bypass n-challenge
        if cookie_file:
            # Try multiple player clients that work with cookies and bypass n-parameter challenge
            # Prioritize 'web' first, then fallback to mobile clients
            player_clients = ['web', 'android_creator', 'ios', 'android']
            
            for client in player_clients:
                print(f"Attempting download with player_client={client}")
                cmd = build_base_cmd(player_client=client)
                result, error = try_download(cmd, f"auto format (player_client={client})")
                if result:
                    return result
                last_error = error
                print(f"ERROR: {client} failed: {str(error)[:100]}")
        else:
            # No cookies - use default auto selection
            cmd = build_base_cmd()
            result, error = try_download(cmd, "auto format selection")
            if result:
                return result
            last_error = error
            print(f"ERROR: Auto format failed: {str(error)[:150]}")
        
        # ATTEMPT 2: List available formats and pick the best non-image format
        print("\n=== Listing available formats ===")
        list_cmd = [YT_DLP_EXE, url, '--list-formats', '--no-check-certificates']
        
        system_proxy = get_system_proxy()
        if system_proxy:
            list_cmd.extend(['--proxy', system_proxy])
        if cookie_file:
            list_cmd.extend(['--cookies', cookie_file])
            # Use android_creator to avoid n-parameter challenge when listing formats
            list_cmd.extend(['--extractor-args', 'youtube:player_client=android_creator'])
        
        try:
            list_process = subprocess.Popen(
                list_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            list_stdout, list_stderr = list_process.communicate()
            
            if list_process.returncode != 0:
                print(f"Failed to list formats: {list_stderr}")
                raise Exception(f"yt-dlp download failed. Last error: {last_error}")
            
            print("Available formats:")
            for line in list_stdout.splitlines()[:20]:  # Show first 20 lines
                print(f"  {line}")
            
            # Parse formats and find best non-image format
            available_formats = []
            for line in list_stdout.splitlines():
                line_lower = line.lower()
                line_stripped = line.strip()
                
                # Skip log lines (start with '['), headers, separators, and image formats
                if (line_stripped.startswith('[') or 
                    any(skip in line_lower for skip in ['format code', '---', 'id  ', 'images only', 'storyboard', 'mhtml', '[info]', '[youtube]'])):
                    continue
                
                parts = line.split()
                if parts and len(parts) >= 2:
                    format_id = parts[0]
                    format_note = ' '.join(parts[1:]).lower()
                    
                    # Skip image-only formats and corrupted/unavailable
                    if any(img in format_note for img in ['jpeg', 'jpg', 'webp', 'png', 'images', 'storyboard', 'unavailable']):
                        continue
                    
                    available_formats.append((format_id, format_note))
            
            if not available_formats:
                raise Exception(
                    "No video/audio formats available (only storyboard images found). "
                    "This video may be restricted, age-gated, private, or require additional authentication. "
                    "Please verify the video is publicly accessible and try providing valid cookies if needed."
                )
            
            print(f"\nFound{len(available_formats)} non-image formats")
            
            # Try to find best format
            # Priority: video+audio > video only > audio only
            best_format = None
            for fmt_id, fmt_note in available_formats:
                if ('video' in fmt_note or 'mp4' in fmt_note or 'webm' in fmt_note) and 'audio' in fmt_note:
                    best_format = fmt_id
                    print(f"Selected video+audio format: {fmt_id}")
                    break
            
            if not best_format:
                # Try video only
                for fmt_id, fmt_note in available_formats:
                    if 'video' in fmt_note or 'mp4' in fmt_note or 'webm' in fmt_note:
                        best_format = fmt_id
                        print(f"Selected video-only format: {fmt_id}")
                        break
            
            if not best_format:
                # Try audio only
                for fmt_id, fmt_note in available_formats:
                    if 'audio' in fmt_note or 'm4a' in fmt_note or 'mp3' in fmt_note:
                        best_format = fmt_id
                        print(f"Selected audio-only format: {fmt_id}")
                        break
            
            if not best_format and available_formats:
                # Just pick the first available
                best_format = available_formats[0][0]
                print(f"Selected first available format: {best_format}")
            
            if best_format:
                cmd = build_base_cmd(best_format)
                result, error = try_download(cmd, f"listed format {best_format}")
                if result:
                    return result
                last_error = error
                print(f"ERROR: Listed format {best_format} failed: {str(error)[:150]}")
        except Exception as e:
            print(f"Format listing fallback failed: {e}")
            last_error = str(e)

        msg = f"yt-dlp download failed after all attempts. Last error: {last_error}"
        try:
            print(msg)
        except UnicodeEncodeError:
            print("ERROR: yt-dlp download failed. Error message contains unencodable characters.")
        raise Exception(msg)

    except Exception as e:
        import traceback
        try:
            print(f"Error in download_video: {e}")
        except UnicodeEncodeError:
            print("Error in download_video: (unencodable characters)")
        traceback.print_exc()
        raise e
    finally:
        if cookie_file and os.path.exists(cookie_file):
            try:
                os.remove(cookie_file)
                print(f"Deleted temp cookie file: {cookie_file}")
            except: pass


if __name__ == "__main__":
    # Test
    url = "https://www.youtube.com/watch?v=Kdql4I-NJ0M" 
    try:
        result = download_video(url)
        print(f"Downloaded: {result}")
    except Exception as e:
        print(f"Error: {e}")
