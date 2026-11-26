@echo off
rem Compila G3G3AI en este PC: doble clic. Deja el resultado en la carpeta dist.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0compilar-windows.ps1" %*
echo.
pause
