@echo off
chcp 65001 >nul
call "%~dp0启动.bat"
exit /b %errorlevel%
