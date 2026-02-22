from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import psutil
import asyncio
import logging

logger = logging.getLogger(__name__)

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
except Exception as e:
    logger.warning(f"NVML could not be initialized: {e}")
    HAS_NVML = False

router = APIRouter(prefix="/system", tags=["System"])

import threading
import time

# Global cache for hardware stats
LATEST_HARDWARE_STATS = {
    "cpu": {"percent": 0.0, "cores": psutil.cpu_count(logical=True)},
    "memory": {"percent": 0.0, "used": 0, "total": 0},
    "gpu": None
}

def _stats_collector_loop():
    """Background thread to collect system stats periodically."""
    global LATEST_HARDWARE_STATS
    # Initialize psutil
    psutil.cpu_percent(interval=None)
    while True:
        try:
            # We use a small interval here in the thread so it doesn't block anything else
            # psutil.cpu_percent(interval=1) in a thread is fine.
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            stats = {
                "cpu": {
                    "percent": cpu_percent,
                    "cores": psutil.cpu_count(logical=True)
                },
                "memory": {
                    "percent": memory.percent,
                    "used": memory.used,
                    "total": memory.total
                },
                "gpu": None
            }
            
            if HAS_NVML:
                gpus = []
                try:
                    device_count = pynvml.nvmlDeviceGetCount()
                    for i in range(device_count):
                        handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                        name = pynvml.nvmlDeviceGetName(handle)
                        if isinstance(name, bytes):
                            name = name.decode('utf-8')
                            
                        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        gpus.append({
                            "id": i,
                            "name": name,
                            "load": util.gpu,
                            "memory_percent": round((mem.used / mem.total) * 100, 2) if mem.total > 0 else 0,
                            "memory_total": mem.total,
                            "memory_used": mem.used,
                            "memory_free": mem.free
                        })
                    stats["gpu"] = gpus
                except Exception as e:
                    stats["gpu_error"] = str(e)
            
            LATEST_HARDWARE_STATS = stats
        except Exception as e:
            logger.error(f"Error in stats collector thread: {e}")
        
        time.sleep(0.5) # Update frequency

# Start the background collector thread
stats_thread = threading.Thread(target=_stats_collector_loop, daemon=True)
stats_thread.start()

@router.get("/status")
async def status():
    """Get current system status (Cached)."""
    return LATEST_HARDWARE_STATS

@router.websocket("/ws/status")
async def status_websocket(websocket: WebSocket):
    """WebSocket for real-time system status updates (from cache)."""
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(LATEST_HARDWARE_STATS)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass
from app.core.logging_config import LOG_FILE

@router.websocket("/ws/logs")
async def logs_websocket(websocket: WebSocket):
    """WebSocket for real-time log streaming from file."""
    await websocket.accept()
    
    try:
        # 1. Send initial history (last 100 lines)
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                # Read all lines and take last 100
                lines = f.readlines()
                for line in lines[-100:]:
                    await websocket.send_text(line.strip())
        
        # 2. Tail the file
        # We'll use a simple polling tail for maximum compatibility across OSes
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                # Move to end of file
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        await asyncio.sleep(0.5) # Wait for new logs
                        continue
                    await websocket.send_text(line.strip())
        else:
            await websocket.send_text("Log file not found yet...")
            while not LOG_FILE.exists():
                await asyncio.sleep(1)
            # Re-run logic if file is created
            await logs_websocket(websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Logs WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass
