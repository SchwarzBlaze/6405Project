@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_study_lens.ps1"
if errorlevel 1 (
    echo.
    echo Study Lens failed to start.
    pause
)

endlocal
