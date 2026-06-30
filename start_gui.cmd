@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw desktop_app.py
) else (
  start "" py desktop_app.py
)
