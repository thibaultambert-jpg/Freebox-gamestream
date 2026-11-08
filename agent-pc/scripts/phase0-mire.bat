@echo off
REM ============================================================
REM  Phase 0 - mire de test (sans capture ni GPU) -> UDP
REM  Utile pour valider le reseau et le lecteur du Player.
REM  Usage : phase0-mire.bat IP_DU_PLAYER
REM ============================================================
if "%~1"=="" (
  echo Usage : %~nx0 IP_DU_PLAYER
  exit /b 1
)
ffmpeg -hide_banner -re -f lavfi -i testsrc2=size=1280x720:rate=60 -vf format=yuv420p ^
  -c:v libx264 -preset ultrafast -tune zerolatency -b:v 8M -maxrate 8M -bufsize 400k -g 60 -bf 0 ^
  -flush_packets 1 -muxdelay 0 -muxpreload 0 -f mpegts "udp://%~1:1234?pkt_size=1316"
