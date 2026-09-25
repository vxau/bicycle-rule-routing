@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Preparing Python environment...
if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv >nul 2>nul
    if errorlevel 1 (
        python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>nul
        if errorlevel 1 goto python_error
        python -m venv .venv
        if errorlevel 1 goto python_error
    )
)
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto python_error

set "PIP_CACHE_DIR=%CD%\.cache\pip"
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 goto install_error

echo [2/3] Preparing settings...
if not exist ".env" copy ".env.example" ".env" >nul
if not exist ".env" goto settings_error

echo [3/3] Checking road data...
if not exist "data\raw\sample_bike.graphml" goto fetch_data
if not exist "data\exports\sample_edges.geojson" goto fetch_data
goto done

:fetch_data
echo Downloading road data. This requires an internet connection.
".venv\Scripts\python.exe" -m backend.scripts.fetch_osm_sample
if errorlevel 1 goto fetch_error

:done
echo.
echo Setup complete. Double-click start_app.bat to open the app.
echo To change the study area, double-click settings.bat.
pause
exit /b 0

:python_error
echo Python 3.10-3.12 is required. Install Python 3.12 and run setup.bat again.
goto failed
:install_error
echo Package installation failed. Check the internet connection and run setup.bat again.
goto failed
:settings_error
echo Could not create .env. Check that .env.example is present.
goto failed
:fetch_error
echo Road download failed. Check the internet connection and run setup.bat again.
goto failed
:failed
pause
exit /b 1
