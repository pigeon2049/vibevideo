@echo off
echo Starting Vibe Video...

:: Start Backend
start "Vibe Video Backend" cmd /k "cd backend && pip install -r requirements.txt && python main.py"

:: Start Frontend
start "Vibe Video Frontend" cmd /k "cd frontend && npm install && npm run dev"

echo Services started! 
echo Frontend: http://localhost:5173
echo Backend: http://localhost:8000
pause
