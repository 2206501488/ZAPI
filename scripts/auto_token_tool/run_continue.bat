@echo off
cd /d "%~dp0"
set PYTHONPATH=%CD%\src

echo Auto Token Tool - continue chain mode
echo Press Ctrl+C to stop.
echo.

:loop
python -B -m auto_token_tool.cli chain
if errorlevel 1 goto failed

echo.
echo Chain run finished. Starting next round in 5 seconds...
timeout /t 5 /nobreak >nul
goto loop

:failed
echo.
echo Chain run failed. Check the error above.
pause
