@echo off
rem usage: auditconf.bat "PDF folder" "result.xlsx"
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python -m engine.cli %1 -o %2
pause
