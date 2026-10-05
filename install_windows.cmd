@echo off
setlocal
chcp 65001 >nul
set "DC_POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe" set "DC_POWERSHELL=%SystemRoot%\Sysnative\WindowsPowerShell\v1.0\powershell.exe"
"%DC_POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows.ps1" %*
set "DC_RESULT=%ERRORLEVEL%"
if not "%DC_RESULT%"=="0" echo Installation failed. See the message above.
pause
exit /b %DC_RESULT%
