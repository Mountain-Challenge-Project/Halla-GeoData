@echo off
setlocal
cd /d "%~dp0"
set "TASK_QGIS_PYTHON="
for /d %%D in ("C:\Program Files\QGIS*") do if exist "%%~D\bin\python-qgis.bat" set "TASK_QGIS_PYTHON=%%~D\bin\python-qgis.bat"
if defined TASK_QGIS_PYTHON (
    call "%TASK_QGIS_PYTHON%" -X utf8 "%~dp0kma_client.py" %*
    exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -X utf8 "%~dp0kma_client.py" %*
    exit /b
)
python -X utf8 "%~dp0kma_client.py" %*
