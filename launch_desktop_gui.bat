@echo off
title Personal Memory Companion - Security Center
cd /d "%~dp0"
echo Starting Local Privacy & Security Module Desktop GUI...
call .venv\Scripts\python.exe -m local_security.ui.app
pause
