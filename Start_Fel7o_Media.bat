@echo off
title Fel7o Media Pro Bot
color 0b
echo ========================================================
echo         FEL7O MEDIA PRO - STUDIO MASTER BOT
echo ========================================================
echo.
cd /d "%~dp0"
python -u main.py >> "%~dp0bot-runtime.log" 2>> "%~dp0bot-runtime-error.log"
