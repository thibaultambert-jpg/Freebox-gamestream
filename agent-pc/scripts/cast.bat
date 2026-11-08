@echo off
REM ============================================================
REM  Mode video seule : envoie l'ecran du PC au lecteur natif du
REM  Freebox Player via AirMedia (aucune app a installer).
REM  Premiere fois : cast.bat pair   (puis valider sur la Freebox Server)
REM  Ensuite      : cast.bat          (flux HTTP)
REM                cast.bat test     (essaie tous les transports)
REM                cast.bat udp-multicast
REM ============================================================
cd /d "%~dp0.."
set CFG=
if exist config.json set CFG=--config config.json
if /i "%~1"=="pair" (
  .venv\Scripts\python.exe -m freestream %CFG% --freebox-pair
) else if /i "%~1"=="test" (
  .venv\Scripts\python.exe -m freestream %CFG% --cast-try-all %2 %3 %4
) else if "%~1"=="" (
  .venv\Scripts\python.exe -m freestream %CFG% --cast http
) else (
  .venv\Scripts\python.exe -m freestream %CFG% --cast %*
)
pause
