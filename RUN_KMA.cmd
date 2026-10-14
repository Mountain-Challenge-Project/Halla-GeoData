@echo off
setlocal
cd /d "%~dp0"
rem Use standard Python for HTTPS. QGIS remains the map/GDAL runtime only.
where py >nul 2>nul
if not errorlevel 1 goto try_py
goto try_python
:try_py
py -3 -c "import sys; assert sys.version_info[:2] >= (3,10)" >nul 2>nul
if errorlevel 1 goto try_python
py -3 -X utf8 "%~dp0kma_client.py" %*
exit /b %errorlevel%
:try_python
where python >nul 2>nul
if errorlevel 1 goto missing
python -c "import sys; assert sys.version_info[:2] >= (3,10)" >nul 2>nul
if errorlevel 1 goto missing
python -X utf8 "%~dp0kma_client.py" %*
exit /b %errorlevel%
:missing
echo Standard Python 3.10 or newer was not found. Install Python and retry.
echo QGIS Python is reserved for START_LOCAL.cmd, not HTTPS collection.
exit /b 1
