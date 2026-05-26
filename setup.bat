@echo off
echo.
echo  ╔═══════════════════════════════════════╗
echo  ║          S E R I A L  A I             ║
echo  ║           Setup Script                ║
echo  ╚═══════════════════════════════════════╝
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.10+ not found. Install from python.org
    pause
    exit /b 1
)

echo [1/4] Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt

echo [3/4] Checking .env file...
if not exist .env (
    copy .env.example .env
    echo [!] Created .env — please add your GEMINI_API_KEY before running!
    notepad .env
) else (
    echo [OK] .env found
)

echo [4/4] Setup complete!
echo.
echo  To run SERIAL AI:
echo    venv\Scripts\activate
echo    python main.py
echo.
echo  For browser mode:
echo    python main.py --browser
echo.
pause
