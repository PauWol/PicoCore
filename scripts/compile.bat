@echo off
setlocal

REM --------------------------
REM compile.bat (fixed - no nested IF parentheses)
REM --------------------------

REM Move to script folder (makes relative paths reliable)
pushd "%~dp0" 2>nul || (
  echo Failed to change directory to script location "%~dp0"
  pause
  goto :EOF
)
set "SCRIPT_DIR=%CD%"

REM Python builder script (relative to this .bat)
set "PYTHON_SCRIPT=%SCRIPT_DIR%\to-mpy.py"

REM Source and build directories (adjust if needed)
set "SRC_DIR=C:\Users\paul2\Documents\Programieren\Raspberry-Pi\Pico\PicoCore V2\src\core"
set "BUILD_DIR=C:\Users\paul2\Documents\Programieren\Raspberry-Pi\Pico\PicoCore V2\build\core"

REM Version filenames
set "SRC_VER_FILE=%SRC_DIR%\.version"
set "BUILD_VER_FILE=%BUILD_DIR%\.version"

echo.
echo [INFO] Script directory: "%SCRIPT_DIR%"
echo [INFO] Source dir:       "%SRC_DIR%"
echo [INFO] Build dir:        "%BUILD_DIR%"
echo.

REM Read source version (if present)
set "SRC_VER="
if exist "%SRC_VER_FILE%" (
  for /f "usebackq delims=" %%A in ("%SRC_VER_FILE%") do set "SRC_VER=%%A"
)

REM Read build version (if present)
set "BUILD_VER="
if exist "%BUILD_VER_FILE%" (
  for /f "usebackq delims=" %%B in ("%BUILD_VER_FILE%") do set "BUILD_VER=%%B"
)

echo [VERSION] Source: "%SRC_VER%"
echo [VERSION] Build : "%BUILD_VER%"
echo.

REM -- Decide status without nested parentheses --
if "%SRC_VER%"=="" goto NO_SRC_VER
if "%BUILD_VER%"=="" goto NO_BUILD_VER

if "%SRC_VER%"=="%BUILD_VER%" goto VERSIONS_MATCH
goto VERSIONS_DIFFER

:NO_SRC_VER
echo [WARN] No .version file found in source dir "%SRC_DIR%".
echo [WARN] After a successful build the script will write a timestamp into the build .version file.
goto ASK_DELETE

:NO_BUILD_VER
echo [INFO] No version found in build dir (will build).
goto ASK_DELETE

:VERSIONS_MATCH
echo [INFO] Versions match. Build looks up-to-date.
goto ASK_DELETE

:VERSIONS_DIFFER
echo [INFO] Versions differ. Source=%SRC_VER%  Build=%BUILD_VER%
goto ASK_DELETE

:ASK_DELETE
echo.
echo WARNING: this may delete files inside "%BUILD_DIR%".
where choice >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  choice /M "Delete build dir contents before rebuilding?"
  if %ERRORLEVEL% EQU 1 (
    set "DO_DELETE=1"
  ) else (
    set "DO_DELETE=0"
  )
) else (
  set "DO_DELETE=0"
  set /P USERRESP=Delete build dir contents before rebuilding? [y/N]:
  if /I "%USERRESP%"=="y" set "DO_DELETE=1"
)

if "%DO_DELETE%"=="1" (
  echo Deleting "%BUILD_DIR%" ...
  rmdir /s /q "%BUILD_DIR%" 2>nul
) else (
  echo Skipping deletion of build dir.
)

REM Ensure build dir exists
if not exist "%BUILD_DIR%" (
  mkdir "%BUILD_DIR%" 2>nul
)

REM Find python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
  set "PY_CMD=python"
) else (
  where py >nul 2>&1
  if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=py"
  ) else (
    echo ERROR: Python not found on PATH. Install or add to PATH.
    popd
    pause
    goto :EOF
  )
)

echo.
echo Running:
echo   %PY_CMD% "%PYTHON_SCRIPT%" "%SRC_DIR%" "%BUILD_DIR%"
echo.

"%PY_CMD%" "%PYTHON_SCRIPT%" "%SRC_DIR%" "%BUILD_DIR%"
set "RC=%ERRORLEVEL%"

if "%RC%" NEQ "0" (
  echo.
  echo ERROR: build script returned code %RC%. Aborting version update.
  popd
  pause
  goto :EOF
)

REM On success, write version info into build .version
if not exist "%BUILD_DIR%" mkdir "%BUILD_DIR%" 2>nul

if "%SRC_VER%"=="" (
  REM No source .version — write current timestamp instead
  ( echo %DATE% %TIME% ) > "%BUILD_VER_FILE%"
) else (
  ( echo %SRC_VER% ) > "%BUILD_VER_FILE%"
)

echo.
echo Build finished successfully.
echo Build-version written to "%BUILD_VER_FILE%".
popd
pause
exit /b 0
