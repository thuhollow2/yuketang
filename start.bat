@echo off
rem Windows 一键启动：固定 UTF-8、关闭输出缓冲、优先使用项目内 venv。
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

title Yuketang Assistant
echo Starting... 登录二维码会保存到 data\qr\qrcode_main.jpg
echo.
"%PY%" -u main.py
echo.
echo Process exited. Press any key to close.
pause >nul
