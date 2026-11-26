@echo off
rem Starts the CIVI speech service (port 8001, this laptop only) and backend (port 8000, Wi-Fi) in two windows.
rem Double-click this file, or run it from a terminal in the repository folder.
cd /d "%~dp0"
if exist "speech_service\.venv\Scripts\python.exe" (
  start "CIVI speech service" cmd /k speech_service\.venv\Scripts\python.exe -m uvicorn civi_speech.main:app --app-dir speech_service --host 127.0.0.1 --port 8001
) else (
  echo Speech service not set up yet: run  py speech_service\setup_speech.py   ^(voice will be unavailable^)
)
start "CIVI backend" cmd /k "cd /d backend && .venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000"
echo Started. Backend: http://127.0.0.1:8000/docs   Speech: http://127.0.0.1:8001/health
