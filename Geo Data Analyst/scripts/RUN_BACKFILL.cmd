@echo off
rem Daily AWS hourly-history backfill (resumable): up to 2,000 day-requests per run, mountain stations first, then all stations since 2023-01-01.
rem   schtasks /Create /SC DAILY /ST 01:00 /TN "Halla-GeoData backfill" /TR "\"%~dp0RUN_BACKFILL.cmd\"" /F
cd /d "%~dp0..\.."
python "Geo Data Analyst\scriptsackfill_aws_hourly.py" --start 2023-01-01 --workers 4 --max-requests 2000 >> runtime\kma\pipeline.log 2>&1
