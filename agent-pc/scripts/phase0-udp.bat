@echo off
REM ============================================================
REM  Phase 0 - test brut sans agent : capture d'ecran -> UDP
REM  Usage : phase0-udp.bat IP_DU_PLAYER [ENCODEUR]
REM    ENCODEUR = h264_nvenc (defaut) | h264_amf | h264_qsv | libx264
REM  Sur le Player, lire : udp://@:1234
REM ============================================================
if "%~1"=="" (
  echo Usage : %~nx0 IP_DU_PLAYER [h264_nvenc^|h264_amf^|h264_qsv^|libx264]
  exit /b 1
)
set PLAYER=%~1
set ENC=%~2
if "%ENC%"=="" set ENC=h264_nvenc

REM Mise a l'echelle 720p en memoire systeme (compatible avec tous les encodeurs)
ffmpeg -hide_banner -filter_complex "ddagrab=output_idx=0:framerate=60,hwdownload,format=bgra,scale=1280:720,format=nv12[v]" -map "[v]" ^
  -c:v %ENC% -b:v 12M -maxrate 12M -bufsize 600k -g 60 -bf 0 ^
  -flush_packets 1 -muxdelay 0 -muxpreload 0 -f mpegts "udp://%PLAYER%:1234?pkt_size=1316"
