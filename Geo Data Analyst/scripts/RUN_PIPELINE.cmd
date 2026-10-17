@echo off
rem Stage 3 pipeline: observations -> forecast -> (KIM levels every 6 h) -> physics on all cells -> station verification archive.
rem Schedule hourly at :45 with Windows Task Scheduler, e.g.
rem   schtasks /Create /SC HOURLY /ST 00:45 /TN "Halla-GeoData pipeline" /TR "\"%~dp0RUN_PIPELINE.cmd\"" /F
rem Needs .env with KMA_API_KEY in the repository root. Logs go to runtime\kma\pipeline.log.
cd /d "%~dp0..\.."
set LOG=runtime\kma\pipeline.log
if not exist runtime\kma mkdir runtime\kma
echo ==== %DATE% %TIME% >> %LOG%
python "Geo Data Analyst\scripts\fetch_kma_obs.py" >> %LOG% 2>&1
python work\fetch_kma_forecast.py >> %LOG% 2>&1
for /f "tokens=1 delims=:" %%h in ("%TIME%") do set HH=%%h
set /a HM=%HH% %% 6
if "%HM%"=="3" python "Geo Data Analyst\scripts\fetch_kim_levels.py" >> %LOG% 2>&1
python "Geo Data Analyst\scripts\compute_stage2.py" >> %LOG% 2>&1
python "Geo Data Analyst\scripts\verify_stations.py" >> %LOG% 2>&1
python work\fetch_kma_warnings.py >> %LOG% 2>&1
