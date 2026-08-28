@echo off
REM One-click Windows build: creates dist\LagScope.exe
setlocal
cd /d "%~dp0.."

python -m venv .venv 2>nul
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python packaging\build.py
if errorlevel 1 (
    echo.
    echo Build failed.
    exit /b 1
)

echo.
echo Built: dist\LagScope.exe
pause
