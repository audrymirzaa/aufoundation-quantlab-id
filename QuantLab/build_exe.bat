@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv-win\Scripts\python.exe" (
  echo Membuat venv Windows...
  python -m venv .venv-win
)

echo Memasang dependensi...
".venv-win\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip
".venv-win\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt pyinstaller pywebview

echo Membangun QuantLab.exe...
".venv-win\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --noconsole --name QuantLab --collect-all webview desktop_launcher.py

if not exist "dist\QuantLab.exe" (
  echo Build gagal. Periksa pesan di atas.
  pause
  exit /b 1
)

copy /y "dist\QuantLab.exe" "QuantLab.exe" >nul
echo Selesai: QuantLab.exe
pause
