@echo off
cd /d "%~dp0"
py build.py || python build.py
pause
