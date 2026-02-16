@echo off
:: Get the directory of the current script
set "SCRIPT_DIR=%~dp0"
:: Set the bin directory relative to the script
set "BIN_DIR=%SCRIPT_DIR%..\bin"

:: Create bin directory if it doesn't exist
if not exist "%BIN_DIR%" (
    echo Creating directory: %BIN_DIR%
    mkdir "%BIN_DIR%"
)

echo Downloading latest yt-dlp.exe from GitHub...
:: Use curl to download. -L follows redirects, -o specifies output file.
curl -L "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -o "%BIN_DIR%\yt-dlp.exe"

if %ERRORLEVEL% equ 0 (
    echo.
    echo Successfully downloaded yt-dlp.exe to: %BIN_DIR%\yt-dlp.exe
) else (
    echo.
    echo Error: Download failed with error level %ERRORLEVEL%
)

pause
