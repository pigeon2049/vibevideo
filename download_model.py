import os
import sys
import requests
from tqdm import tqdm
from pathlib import Path

# 路径配置
PROJECT_ROOT = Path(__file__).resolve().parent
MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# 模型下载地址
# 使用 HF 镜像加速
HF_MIRROR = "https://hf-mirror.com"
GGML_MODELS_BASE = f"{HF_MIRROR}/ggerganov/whisper.cpp/resolve/main"
VAD_MODEL_URL = "https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main/silero_vad.onnx" # Faster-whisper uses onnx
# FFmpeg Whisper tutorial mentions:
# https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/models/for-tests-silero-v5.1.2-ggml.bin
VAD_MODEL_GGML_URL = "https://github.com/ggml-org/whisper.cpp/raw/master/models/for-tests-silero-v5.1.2-ggml.bin"

def download_file(url: str, dest: Path):
    if dest.exists():
        print(f"文件已存在: {dest}")
        return
    
    print(f"正在从 {url} 下载...")
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(dest, 'wb') as f, tqdm(
        total=total_size,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(chunk_size=1024):
            size = f.write(data)
            bar.update(size)

def main():
    model_name = sys.argv[1] if len(sys.argv) > 1 else "base"
    
    # 1. 下载 Whisper GGML 模型
    model_file = f"ggml-{model_name}.bin"
    model_url = f"{GGML_MODELS_BASE}/{model_file}"
    model_path = MODELS_DIR / model_file
    
    print(f"--- 准备下载 Whisper 模型: {model_name} ---")
    try:
        download_file(model_url, model_path)
    except Exception as e:
        print(f"❌ 下载 Whisper 模型失败: {e}")
        
    # 2. 下载 VAD 模型 (用于提高断句准确度)
    vad_path = MODELS_DIR / "ggml-silero-v5.1.2.bin"
    print(f"\n--- 准备下载 VAD 模型 ---")
    try:
        download_file(VAD_MODEL_GGML_URL, vad_path)
    except Exception as e:
        print(f"⚠️ 下载 VAD 模型失败 (可选): {e}")

    print(f"\n✅ 下载完成！")
    print(f"模型存放目录: {MODELS_DIR}")
    print(f"FFmpeg 命令示例: ffmpeg -i input.mp4 -af \"whisper=model=models/{model_file}:vad_model=models/ggml-silero-v5.1.2.bin...\"")

if __name__ == "__main__":
    main()
