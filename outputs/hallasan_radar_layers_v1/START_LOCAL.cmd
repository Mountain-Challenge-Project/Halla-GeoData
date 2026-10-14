@echo off
setlocal
chcp 65001 >nul
set "QGIS_RUN=C:\Program Files\QGIS 4.2.0\bin\python-qgis.bat"
if not exist "%QGIS_RUN%" for /d %%D in ("C:\Program Files\QGIS*") do if exist "%%D\bin\python-qgis.bat" set "QGIS_RUN=%%D\bin\python-qgis.bat"
if not exist "%QGIS_RUN%" (
 echo QGIS Python runtime was not found. Install QGIS or edit QGIS_RUN in this file.
 pause
 exit /b 1
)
cd /d "%~dp0"
echo Open http://127.0.0.1:8765 in your browser after Local appears.
echo Close this window or press Ctrl+C to stop.
call "%QGIS_RUN%" -X utf8 "%~dp0processor.py" serve
pause
