@echo off
rem Collect the current KMA observations for Jeju (AWS 1-min + ASOS hourly) and refresh the forecast.
rem Schedule with Windows Task Scheduler every 10 minutes, e.g.:
rem   schtasks /Create /SC MINUTE /MO 10 /TN "Halla-GeoData obs" /TR "\"%~dp0RUN_OBS.cmd\"" /F
cd /d "%~dp0"
python work\fetch_kma_obs.py
if "%1"=="forecast" python work\fetch_kma_forecast.py
