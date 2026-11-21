@echo off
chcp 65001 >nul
setlocal
title GTA 6 Klipleyici
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "VENV=%LOCALAPPDATA%\gta6klip\venv"
set "LOG=%~dp0son_calisma.log"
echo [%date% %time%] klip.bat acildi> "%LOG%"

if not exist "%VENV%\Scripts\python.exe" goto kurulumyok

echo ============================================
echo   GTA 6 Klipleyici
echo ============================================

:sor
set "LINK="
echo.
echo Yayin linkini yapistir - Ctrl+V ya da sag tik - sonra Enter'a bas:
set /p "LINK=> "
if not defined LINK goto bos

echo [%date% %time%] link alindi, calisiyor>> "%LOG%"
echo.
echo Basladi. Bu pencere acik kaldikca calisiyor demektir.
echo Her adimin saatini asagida goreceksin. KAPATMA.
echo.
"%VENV%\Scripts\python.exe" "%~dp0klipci.py" "%LINK%" %*
echo.
if errorlevel 1 (
  echo HATA OLDU. Bu pencerede yazanlari Claude'a yapistir.
) else (
  echo BITTI. Klipler klasoru aciliyor...
  start "" "%~dp0klipler_cikti"
)
echo.
pause
exit /b

:bos
echo Link bos geldi, yapistirma olmadi. Tekrar dene.
goto sor

:kurulumyok
echo [%date% %time%] kurulum yapilmamis>> "%LOG%"
echo.
echo Kurulum yapilmamis. Once kurulum.bat dosyasina cift tikla,
echo "KURULUM TAMAM" yazisini gorunce bunu tekrar ac.
echo.
pause
