import os
import asyncio
import sys
import tempfile
import subprocess
import json
import urllib.request
import logging
import time
from pathlib import Path
from typing import Dict, Optional
from app.core.config import settings

logger = logging.getLogger("vibe-video.services.downloader")

class DownloaderService:
    def __init__(self):
        self.yt_dlp_exe = str(settings.BIN_DIR / "yt-dlp.exe")
        self.deno_exe = str(settings.BIN_DIR / "deno.exe")
        self.bin_dir = str(settings.BIN_DIR)
        self.video_dir = str(settings.VIDEO_DIR)

    def get_system_proxy(self) -> Optional[str]:
        """Detect system proxy settings on Windows."""
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
        """
        Robust download with fallback strategies and player client rotation.
        """
        if not os.path.exists(self.yt_dlp_exe):
            raise FileNotFoundError(f"yt-dlp.exe not found at {self.yt_dlp_exe}")

        # Check for existing file with this ID first
        info_cmd = [self.yt_dlp_exe, url, '--dump-json', '--no-playlist', '--no-check-certificates']
        proxy = self.get_system_proxy()
        if proxy:
            info_cmd.extend(['--proxy', proxy])
        
        temp_cookie_for_info = None
        try:
            if cookies:
                fd, temp_cookie_for_info = tempfile.mkstemp(suffix=".txt", prefix="info_cookies_")
                with os.fdopen(fd, 'w') as f:
                    f.write(cookies)
                info_cmd.extend(['--cookies', temp_cookie_for_info])

            logger.info(f"Fetching video info for: {url}")
            process = await asyncio.create_subprocess_exec(
                *info_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_bytes, stderr_bytes = await process.communicate()
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            
            if process.returncode == 0:
                video_info = json.loads(stdout)
                video_id = video_info.get('id')
                title = video_info.get('title', 'Unknown')
                
                if video_id:
                    for f in os.listdir(self.video_dir):
                        if f.startswith(f"{video_id}."):
                            existing_path = os.path.join(self.video_dir, f)
                            logger.info(f"Found existing download: {existing_path}")
                            return {
                                "title": title,
                                "duration": video_info.get("duration", 0),
                                "path": os.path.abspath(existing_path),
                                "thumbnail": video_info.get("thumbnail"),
                                "id": video_id
                            }
            else:
                logger.warning(f"Could not fetch video info: {stderr}")
        except Exception as e:
            logger.error(f"Error checking for existing download: {e}")
        finally:
            if temp_cookie_for_info and os.path.exists(temp_cookie_for_info):
                os.remove(temp_cookie_for_info)

        # Main download logic
        cookie_file = None
        if cookies:
            fd, cookie_file = tempfile.mkstemp(suffix=".txt", prefix="cookies_")
            with os.fdopen(fd, 'w') as f:
                f.write(cookies)

        try:
            def build_cmd(format_spec=None, player_client=None):
                outtmpl = os.path.join(self.video_dir, "%(id)s.%(ext)s")
                cmd = [
                    self.yt_dlp_exe, url,
                    '--output', outtmpl,
                    '--no-playlist',
                    '--print-json',
                    '--no-check-certificates',
                    '--ffmpeg-location', self.bin_dir,
                    '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                ]
                if os.path.exists(self.deno_exe):
                    cmd.extend(['--js-runtimes', f'deno:{self.deno_exe}'])
                if format_spec:
                    cmd.extend(['--format', format_spec])
                if proxy:
                    cmd.extend(['--proxy', proxy])
                if cookie_file:
                    cmd.extend(['--cookies', cookie_file])
                    client = player_client or 'android_creator'
                    cmd.extend(['--extractor-args', f'youtube:player_client={client}'])
                return cmd

            last_error = ""
            # ATTEMPT 1: Try rotation of player clients
            clients = ['web', 'android_creator', 'ios', 'android'] if cookie_file else [None]
            for client in clients:
                cmd = build_cmd(player_client=client)
                logger.info(f"Attempting download with client: {client or 'default'}")
                p = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                out_bytes, err_bytes = await p.communicate()
                out = out_bytes.decode('utf-8', errors='replace')
                err = err_bytes.decode('utf-8', errors='replace')
                if p.returncode == 0:
                    info = json.loads(out)
                    return {
                        "title": info.get("title", "Unknown"),
                        "duration": info.get("duration", 0),
                        "path": os.path.abspath(info.get("_filename")),
                        "thumbnail": info.get("thumbnail"),
                        "id": info.get("id")
                    }
                last_error = err
                logger.warning(f"Client {client or 'default'} failed: {err[:200]}")

            # ATTEMPT 2: Fallback to listed formats
            list_cmd = [self.yt_dlp_exe, url, '--list-formats', '--no-check-certificates']
            if proxy: list_cmd.extend(['--proxy', proxy])
            if cookie_file: 
                list_cmd.extend(['--cookies', cookie_file])
                list_cmd.extend(['--extractor-args', 'youtube:player_client=android_creator'])
            
            lp = await asyncio.create_subprocess_exec(
                *list_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            lout_bytes, lerr_bytes = await lp.communicate()
            lout = lout_bytes.decode('utf-8', errors='replace')
            lerr = lerr_bytes.decode('utf-8', errors='replace')
            if lp.returncode == 0:
                best_fmt = None
                # Simple priority: video+audio (mp4/webm)
                for line in reversed(lout.splitlines()):
                    if 'video' in line.lower() and 'audio' in line.lower() and ('mp4' in line.lower() or 'webm' in line.lower()):
                        best_fmt = line.split()[0]
                        break
                if best_fmt:
                    cmd = build_cmd(format_spec=best_fmt)
                    p = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    out_bytes, err_bytes = await p.communicate()
                    out = out_bytes.decode('utf-8', errors='replace')
                    err = err_bytes.decode('utf-8', errors='replace')
                    if p.returncode == 0:
                        info = json.loads(out)
                        return {
                            "title": info.get("title", "Unknown"),
                            "duration": info.get("duration", 0),
                            "path": os.path.abspath(info.get("_filename")),
                            "thumbnail": info.get("thumbnail"),
                            "id": info.get("id")
                        }

            raise Exception(f"Download failed after all attempts. Last error: {last_error}")

        finally:
            if cookie_file and os.path.exists(cookie_file):
                os.remove(cookie_file)


downloader_service = DownloaderService()

