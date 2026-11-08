@echo off
REM Lance l'agent FreeStream avec config.json (cree par install.ps1)
cd /d "%~dp0.."
if exist config.json (
  .venv\Scripts\python.exe -m freestream --config config.json %*
) else (
  .venv\Scripts\python.exe -m freestream %*
)
pause
