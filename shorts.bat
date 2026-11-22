@echo off
chcp 65001 >nul
setlocal
title GTA 6 Viral Videolar - Turkce Altyazi
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "VENV=%LOCALAPPDATA%\gta6klip\venv"
set "LOG=%~dp0son_calisma.log"
echo [%date% %time%] shorts.bat acildi> "%LOG%"

if not exist "%VENV%\Scripts\python.exe" goto kurulumyok

echo ============================================
echo   GTA 6 Viral Videolar - Turkce Altyazi
echo ============================================
echo.
echo YouTube Shorts, Instagram Reels ve TikTok'tan son bir
echo haftanin en cok izlenen yabanci GTA 6
echo videolarini bulur, ayni videonun kopyalarini birlestirir,
echo Turkce altyazili hale getirir.
echo.
echo Belirli bir videoyu yapmak istersen linkini yapistir
echo (YouTube, TikTok ya da Instagram).
echo Otomatik bulsun istiyorsan bos birakip Enter'a bas:
set "LINK="
set /p "LINK=> "
echo.
echo Basladi. Bu pencere acik kaldikca calisiyor demektir. KAPATMA.
echo.
if defined LINK (
  "%VENV%\Scripts\python.exe" "%~dp0shorts.py" --link "%LINK%" %*
) else (
  "%VENV%\Scripts\python.exe" "%~dp0shorts.py" %*
)
echo.
if errorlevel 1 (
  echo HATA OLDU ya da uygun video bulunamadi. Bu pencerede yazanlari Claude'a yapistir.
) else (
  echo BITTI. Klasor aciliyor...
  start "" "%~dp0klipler_cikti\shorts"
)
echo.
pause
exit /b

:kurulumyok
echo.
echo Kurulum yapilmamis. Once kurulum.bat dosyasina cift tikla,
echo "KURULUM TAMAM" yazisini gorunce bunu tekrar ac.
echo.
pause
