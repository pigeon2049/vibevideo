@echo off
setlocal
cd /d %~dp0
set HF_ENDPOINT=https://hf-mirror.com

echo ==========================================
echo    Whisper 模型下载工具 (镜像加速版)
echo ==========================================
echo.
echo 正在尝试下载 large-v3 模型...
echo 如果下载不动，请确保已安装 python 和相关依赖。
echo.

python backend\download_model.py large-v3

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [错误] 下载失败。请检查网络或 Python 环境。
    pause
) else (
    echo.
    echo [成功] 模型已下载完成。
    pause
)
