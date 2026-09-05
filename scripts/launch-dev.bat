@echo off
chcp 65001 >nul
call "%~dp0启动-开发模式.bat"
exit /b %errorlevel%
