@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto missing_setup
if not exist "data\raw\sample_bike.graphml" goto missing_data
if not exist "data\input\od_pairs.csv" goto missing_od

echo Screening cycling-facility improvements with a 1000 m budget...
".venv\Scripts\python.exe" -m backend.scripts.optimize_facilities
if errorlevel 1 goto placement_error

echo Results are in data\processed\facility_candidates.csv and
echo data\processed\facility_placement_summary.json.
pause
exit /b 0

:missing_setup
echo Run setup.bat first.
goto failed
:missing_data
echo Road data is missing. Run setup.bat or settings.bat.
goto failed
:missing_od
echo OD pairs are missing. Run the OD generator as described in README.md.
goto failed
:placement_error
echo Candidate screening failed. Check the message above.
:failed
pause
exit /b 1
