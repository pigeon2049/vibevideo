import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Paths
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "app.log"
LOG_DIR.mkdir(exist_ok=True)

def setup_logging():
    # Base configuration
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    # 1. Console Handler (Stdout)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    
    # 2. File Handler (Persistent)
    file_handler = RotatingFileHandler(
        str(LOG_FILE), 
        maxBytes=10*1024*1024, # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    
    # Root logger setup
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clean up existing handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    
    # Configure uvicorn loggers to use our file handler and console
    # By making them children of root OR settings their handlers explicitly
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        uv_logger = logging.getLogger(logger_name)
        uv_logger.handlers = []
        # Propagate to root logger which has the file/stream handlers
        uv_logger.propagate = True
        uv_logger.setLevel(logging.INFO)

    logging.getLogger("vibe-video").info(f"Logging initialized. Logs stored in {LOG_FILE}")

logger = logging.getLogger("vibe-video")
