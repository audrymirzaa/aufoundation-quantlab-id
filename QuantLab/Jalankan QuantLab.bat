@echo off
setlocal EnableExtensions DisableDelayedExpansion
title QuantLab Launcher
set "PORT=8501"
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"
cd /d "%APP_DIR%"

echo Memulai QuantLab...

set "PYTHON="
if exist ".venv-win\Scripts\python.exe" set "PYTHON=.venv-win\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

if defined PYTHON (
  start "QuantLab Server" "%PYTHON%" -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port %PORT%
  goto wait
)

where python >nul 2>&1
if not errorlevel 1 (
  start "QuantLab Server" python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port %PORT%
  goto wait
)

where wsl >nul 2>&1
if errorlevel 1 (
  echo Python tidak ditemukan. Install Python 3.12 lalu jalankan: pip install -r requirements.txt
  pause
  exit /b 1
)

for /f "usebackq delims=" %%I in (`wsl wslpath -u "%APP_DIR%"`) do set "WSL_DIR=%%I"
start "QuantLab Server" wsl bash -lc "cd '%WSL_DIR%' && exec .venv/bin/python -m streamlit run app.py --server.headless true --server.address 127.0.0.1 --server.port %PORT%"

:wait
echo Menunggu server siap. Pertama kali bisa 30-60 detik...
for /l %%i in (1,1,90) do (
  timeout /t 2 /nobreak >nul
  powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%PORT%' -TimeoutSec 2; if($r.StatusCode -eq 200){exit 0}else{exit 1} } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 goto ready
)

echo Server belum siap. Cek jendela "QuantLab Server" untuk pesan error.
pause
exit /b 1

:ready
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" (
  start "" "%EDGE%" --app=http://127.0.0.1:%PORT%
) else (
  start "" http://127.0.0.1:%PORT%
)
echo QuantLab sudah terbuka.
echo Untuk menghentikan, tutup jendela "QuantLab Server".
timeout /t 5 >nul
exit /b 0
