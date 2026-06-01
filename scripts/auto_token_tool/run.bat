@echo off
cd /d "%~dp0"
set PYTHONPATH=%CD%\src
python -B -m auto_token_tool.cli
pause
