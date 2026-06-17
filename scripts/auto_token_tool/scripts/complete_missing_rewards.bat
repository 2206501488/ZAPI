@echo off
cd /d "%~dp0\.."
set PYTHONPATH=%CD%\src

python -B scripts\complete_missing_rewards.py %*
pause
