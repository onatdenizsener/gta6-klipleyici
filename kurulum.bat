@echo off
chcp 65001 >nul
setlocal
title GTA 6 Klipleyici - Kurulum
set "VENV=%LOCALAPPDATA%\gta6klip\venv"

echo ============================================
echo   GTA 6 Klipleyici - Kurulum (tek seferlik)
echo ============================================
echo.

set "PY="
if exist "%USERPROFILE%\anaconda3\python.exe" set "PY=%USERPROFILE%\anaconda3\python.exe"
if not defined PY (
  where py >nul 2>&1 && set "PY=py"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [HATA] Python bulunamadi. python.org'dan Python 3.11 kurup tekrar dene.
  pause
  exit /b 1
)
echo Python: %PY%

if not exist "%VENV%\Scripts\python.exe" (
  echo [1/3] Sanal ortam olusturuluyor...
  "%PY%" -m venv "%VENV%"
  if errorlevel 1 (
    echo [HATA] Sanal ortam olusturulamadi.
    pause
    exit /b 1
  )
)

echo [2/3] Paketler kuruluyor (yt-dlp, Whisper, OpenCV...) birkac dakika surer...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip -q
"%VENV%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo [HATA] Paket kurulumu basarisiz.
  pause
  exit /b 1
)

echo [3/3] FFmpeg kontrol ediliyor...
where ffmpeg >nul 2>&1
if errorlevel 1 (
  if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe" (
    echo FFmpeg zaten kurulu.
  ) else (
    echo FFmpeg kuruluyor - winget...
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
  )
) else (
  echo FFmpeg zaten kurulu.
)

echo.
echo Whisper modeli ilk klipte otomatik inecek (~500 MB, bir kere).
echo.
echo kurulum tamam %date% %time%> "%~dp0kurulum_tamam.txt"
echo KURULUM TAMAM. Simdi klip.bat'a cift tikla.
pause
