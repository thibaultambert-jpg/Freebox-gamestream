@echo off
REM ============================================================
REM  Phase 0 - test brut sans agent : capture d'ecran -> HTTP
REM  FFmpeg joue le role de serveur HTTP (un seul client).
REM  Sur le Player, lire : http://IP_DU_PC:8080/live.ts
REM  Usage : phase0-http.bat [ENCODEUR]
REM ============================================================
set ENC=%~1
if "%ENC%"=="" set ENC=h264_nvenc
ffmpeg -hide_banner -filter_complex "ddagrab=output_idx=0:framerate=60,hwdownload,format=bgra,scale=1280:720,format=nv12[v]" -map "[v]" ^
  -c:v %ENC% -b:v 12M -maxrate 12M -bufsize 600k -g 60 -bf 0 ^
  -flush_packets 1 -muxdelay 0 -muxpreload 0 -f mpegts -listen 1 "http://0.0.0.0:8080/live.ts"
