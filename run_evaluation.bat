@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto missing_setup
if not exist "data\raw\sample_bike.graphml" goto missing_data
if not exist "data\input\od_pairs.csv" goto missing_od

echo Running Phase 5 route evaluation...
".venv\Scripts\python.exe" -m backend.scripts.evaluate_profiles
if errorlevel 1 goto evaluation_error

echo Results are in data\processed\route_comparison.csv,
echo data\processed\sensitivity_analysis.csv, and
echo data\processed\sensitivity_summary.csv.
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
:evaluation_error
echo Evaluation failed. Check the message above.
:failed
pause
exit /b 1
