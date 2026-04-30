@echo off
:: ═══════════════════════════════════════════════════════════
::  setup_windows.bat  –  Einmalige Einrichtung
:: ═══════════════════════════════════════════════════════════
title PI·HOME Setup
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   PI·HOME Setup  –  Windows          ║
echo  ╚══════════════════════════════════════╝
echo.

:: Python prüfen
echo [1/6] Python prüfen...
python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden!
    echo Bitte python.org/downloads aufrufen.
    echo Wichtig: "Add to PATH" beim Installieren anhaken!
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo        %%i

:: Virtuelle Umgebung
echo [2/6] Virtuelle Umgebung erstellen...
if not exist "venv\" python -m venv venv
call venv\Scripts\activate.bat

:: Pakete
echo [3/6] Pakete installieren (kann etwas dauern)...
pip install --upgrade pip -q
pip install -r requirements.txt -q

:: Ordner
echo [4/6] Ordner prüfen...
if not exist "data\"               mkdir data
if not exist "web\static\"         mkdir web\static

:: Datenbank
echo [5/6] Datenbank initialisieren...
python -c "from core.database import init_db; init_db()"
if errorlevel 1 (
    echo FEHLER bei Datenbankinitialisierung!
    pause & exit /b 1
)

:: Desktop-Verknüpfung
echo [6/6] Desktop-Verknüpfung erstellen...
powershell -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell; ^
   $lnk=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop')+'\PI-HOME Steuerung.lnk'); ^
   $lnk.TargetPath='%~dp0venv\Scripts\pythonw.exe'; ^
   $lnk.Arguments='%~dp0launcher.py'; ^
   $lnk.WorkingDirectory='%~dp0'; ^
   $lnk.IconLocation='shell32.dll,13'; ^
   $lnk.Description='PI-HOME Smarthome starten und stoppen'; ^
   $lnk.Save()"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   Setup abgeschlossen!               ║
echo  ╠══════════════════════════════════════╣
echo  ║                                      ║
echo  ║  Starten:                            ║
echo  ║  Doppelklick auf                     ║
echo  ║  "PI-HOME Steuerung" auf dem         ║
echo  ║  Desktop                             ║
echo  ║                                      ║
echo  ║  Oder manuell:                       ║
echo  ║  venv\Scripts\python.exe main.py     ║
echo  ║                                      ║
echo  ╚══════════════════════════════════════╝
echo.
pause
