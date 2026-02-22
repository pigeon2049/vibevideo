import os
import sys
import tempfile
import subprocess
import json
import urllib.request
import logging
from app.core.config import settings

logger = logging.getLogger("vibe-video.services.downloader")

class DownloaderService:
    def __init__(self):
        self.yt_dlp_exe = settings.BIN_DIR / "yt-dlp.exe"
        self.deno_exe = settings.BIN_DIR / "deno.exe"

    def get_system_proxy(self):
        try:
            proxies = urllib.request.getproxies()
            if proxies:
                proxy = proxies.get('http') or proxies.get('https')
                if proxy:
                    logger.info(f"Detected system proxy: {proxy}")
                    return proxy
            
            if sys.platform == 'win32':
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                       r'Software\Microsoft\Windows\CurrentVersion\Internet Settings') as key:
                        proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')
                        if proxy_enable:
                            proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
                            if proxy_server:
                                if not proxy_server.startswith('http'):
                                    proxy_server = f'http://{proxy_server}'
                                logger.info(f"Detected Windows registry proxy: {proxy_server}")
                                return proxy_server
                except (OSError, FileNotFoundError, ImportError):
                    pass
        except Exception as e:
            logger.error(f"Error detecting proxy: {e}")
        return None

    async def download(self, url: str, cookies: str = None) -> dict:
        if not self.yt_dlp_exe.exists():
            raise FileNotFoundError(f"yt-dlp.exe not found at {self.yt_dlp_exe}")

        # Basic download logic (simplified from old one for clarity)
        # We'll use subprocess.run for simplicity here, though in a real-world app we'd use async subprocess
        
        cookie_file = None
        if cookies:
            fd, cookie_file = tempfile.mkstemp(suffix=".txt", prefix="cookies_")
            with os.fdopen(fd, 'w') as f:
                f.write(cookies)

        try:
            outtmpl = str(settings.VIDEO_DIR / "%(id)s.%(ext)s")
            cmd = [
                str(self.yt_dlp_exe),
                url,
                '--output', outtmpl,
                '--no-playlist',
                '--print-json',
                '--no-check-certificates',
                '--ffmpeg-location', str(settings.BIN_DIR),
            ]

            proxy = self.get_system_proxy()
            if proxy:
                cmd.extend(['--proxy', proxy])
            if cookie_file:
                cmd.extend(['--cookies', cookie_file])

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
                return {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration", 0),
                    "path": info.get("_filename"),
                    "thumbnail": info.get("thumbnail"),
                    "id": info.get("id")
                }
            else:
                raise Exception(f"Download failed: {stderr}")

        finally:
            if cookie_file and os.path.exists(cookie_file):
                os.remove(cookie_file)

downloader_service = DownloaderService()
