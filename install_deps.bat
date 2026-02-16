@echo off
echo ==========================================
echo Vibe Video - Dependency Installer
echo ==========================================

echo [1/2] Installing Backend Dependencies...
cd backend
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install backend dependencies.
    pause
    exit /b %errorlevel%
)
cd ..

echo.
echo [2/2] Installing Frontend Dependencies...
cd frontend
call npm install
if %errorlevel% neq 0 (
    echo Failed to install frontend dependencies.
    pause
    exit /b %errorlevel%
)
cd ..

echo.
echo ==========================================
echo All dependencies installed successfully!
echo You can now run start_app.bat
echo ==========================================
pause
