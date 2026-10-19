@echo off

rem Stage 4: retrain the residual models from the feature archive and apply them to the cells.

rem Needs a Python with scikit-learn (anaconda). Schedule weekly, e.g.

rem   schtasks /Create /SC WEEKLY /D SUN /ST 03:00 /TN "Halla-GeoData train" /TR "\"%~dp0RUN_TRAIN.cmd\"" /F

cd /d "%~dp0..\.."

set PY=%USERPROFILE%naconda3\python.exe

if not exist "%PY%" set PY=python

python "Geo Data Analyst\scriptsuild_training_set_era5.py" >> runtime\kma\pipeline.log 2>&1
"%PY%" "Geo Data Analyst\scripts	rain_residual_model.py" --with-era5 >> runtime\kma\pipeline.log 2>&1

"%PY%" "Geo Data Analyst\scriptspply_residual_model.py" >> runtime\kma\pipeline.log 2>&1

