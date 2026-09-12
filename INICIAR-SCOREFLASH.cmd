@echo off
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-scoreflash.ps1"
if errorlevel 1 pause
