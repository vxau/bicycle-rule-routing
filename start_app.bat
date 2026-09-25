@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto missing_setup
if not exist "data\raw\sample_bike.graphml" goto missing_data
if not exist "data\exports\sample_edges.geojson" goto missing_data
if /i "%~1"=="--check" exit /b 0

echo Starting the app at http://127.0.0.1:8000/
echo Close this window to stop the app.
".venv\Scripts\python.exe" -m backend.scripts.launch_app
if errorlevel 1 goto launch_error
exit /b 0

:missing_setup
echo Run setup.bat first.
goto failed
:missing_data
echo Road data is missing. Run setup.bat again.
goto failed
:launch_error
echo Could not start the app. Check whether port 8000 is already in use.
:failed
pause
exit /b 1
