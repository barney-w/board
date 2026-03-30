@echo off
REM Board — installs the extension and opens your board pass
REM Just double-click this file to get started!

echo.
echo   Setting up Board...
echo.

REM Check VS Code is installed
where code >nul 2>&1
if %errorlevel% neq 0 (
    echo   VS Code not found.
    echo.
    echo   Install it from: https://code.visualstudio.com
    echo   Then re-run this file.
    echo.
    pause
    exit /b 1
)

REM Find the .vsix file
set "VSIX="
for %%f in ("%~dp0*.vsix") do set "VSIX=%%f"
if not defined VSIX (
    echo   ERROR: No .vsix file found in this folder.
    pause
    exit /b 1
)

REM Find the .board-pass file
set "PASS="
for %%f in ("%~dp0*.board-pass") do set "PASS=%%f"
if not defined PASS (
    echo   ERROR: No .board-pass file found in this folder.
    pause
    exit /b 1
)

REM Install extension
echo   Installing Board extension...
code --install-extension "%VSIX%" --force
echo   Done.
echo.

REM Give VS Code time to load the new extension before opening the file
timeout /t 2 /nobreak >nul

REM Open the board pass in VS Code (triggers the import flow)
echo   Opening your board pass in VS Code...
code "%PASS%"
echo.
echo   VS Code should now be asking for your passphrase.
echo   Enter the passphrase your team lead gave you.
echo.
pause
