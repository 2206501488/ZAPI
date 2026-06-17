@echo off
cd /d "%~dp0\.."
set PYTHONPATH=%CD%\src

python -B scripts\claim_final_reward.py %*
pause
