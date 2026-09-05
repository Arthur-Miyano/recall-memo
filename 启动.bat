@echo off
chcp 65001 >nul
REM Hand off immediately: batch files cannot hide their own console.
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\launch-hidden.ps1"
exit /b
