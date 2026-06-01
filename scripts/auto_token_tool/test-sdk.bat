@echo off
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
python -B examples\embed_sdk.py
if errorlevel 1 (
  echo SDK import test failed.
) else (
  echo SDK import test passed.
)
pause
