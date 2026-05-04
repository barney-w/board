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

REM Always install the bundled extension with --force so the version shipped
REM with this pass wins over any older installed version. Idempotent when the
REM bundled version matches what's already installed.
echo   Installing Board extension...
code --install-extension "%VSIX%" --force
echo   Done.
REM Give VS Code time to load the new extension before opening the file
timeout /t 3 /nobreak >nul
echo.

REM Detect auth method from the board pass JSON (requires python3 or python)
set "AUTH_METHOD=ssh-key"
where python3 >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%a in ('python3 -c "import json; print(json.load(open(r'%PASS%')).get('authMethod','ssh-key'))" 2^>nul') do set "AUTH_METHOD=%%a"
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        for /f "delims=" %%a in ('python -c "import json; print(json.load(open(r'%PASS%')).get('authMethod','ssh-key'))" 2^>nul') do set "AUTH_METHOD=%%a"
    )
)

REM Open the board pass in a NEW VS Code window. A new window starts a fresh
REM extension host that loads the freshly installed extension. Without
REM --new-window, any already-open VS Code keeps the previous extension code in
REM memory and the import flow can hit the old (encrypted-only) code path —
REM producing a passphrase prompt for what should be a plaintext Entra ID pass.
echo   Opening your board pass in VS Code...
code --new-window "%PASS%"
echo.
echo   VS Code is now importing your board pass.
if /i "%AUTH_METHOD%"=="entra-id" (
    echo   No passphrase needed - Entra ID handles authentication.
    echo   Click Connect when VS Code is ready.
) else (
    echo   Enter the passphrase your team lead gave you.
)
echo.
pause
