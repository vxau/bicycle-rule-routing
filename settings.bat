@echo off
setlocal
cd /d "%~dp0"

echo Close the app before changing settings.
if not exist ".env" copy ".env.example" ".env" >nul
if not exist ".env" goto missing_settings
notepad.exe ".env"
if not exist ".venv\Scripts\python.exe" goto missing_python

echo Updating road data for the saved settings...
".venv\Scripts\python.exe" -m backend.scripts.fetch_osm_sample
if errorlevel 1 goto fetch_error
echo Road data updated. Double-click start_app.bat to open the app.
pause
exit /b 0

:missing_settings
echo .env.example is missing. Restore the repository files.
goto failed
:missing_python
echo Run setup.bat first.
goto failed
:fetch_error
echo Road download failed. Check .env and the internet connection, then run settings.bat again.
:failed
pause
exit /b 1
