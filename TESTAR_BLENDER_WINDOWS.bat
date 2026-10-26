@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Execute INICIAR_WINDOWS.bat primeiro para preparar o Python.
  pause
  exit /b 1
)
.venv\Scripts\python.exe validar_blender.py
pause
