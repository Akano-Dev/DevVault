@echo off
setlocal EnableExtensions

rem ===================================================================
rem  QuestPanel launcher
rem
rem  Double-click to run. On first launch it installs PySide6 if it is
rem  missing; after that it starts silently with no console window.
rem
rem  Flags:
rem     QuestPanel.bat /console   keep this window open and show output
rem     QuestPanel.bat /exe       run the packaged build in dist\ instead
rem     QuestPanel.bat /reinstall force a dependency reinstall
rem
rem  Running a second copy does not open a second overlay -- the running
rem  one is raised instead.
rem ===================================================================

rem Work from the folder holding this script, whatever the working dir is.
cd /d "%~dp0"

set "CONSOLE="
set "REINSTALL="
set "USEEXE="
:parse
if "%~1"=="" goto parsed
if /i "%~1"=="/console"   set "CONSOLE=1"
if /i "%~1"=="/exe"       set "USEEXE=1"
if /i "%~1"=="/reinstall" set "REINSTALL=1"
shift
goto parse
:parsed

rem --- Packaged build, only when asked for -----------------------------
rem  Source is the default so edits always take effect; a stale dist\ build
rem  silently overriding your changes is a nasty thing to debug.
if defined USEEXE (
    if exist "dist\QuestPanel\QuestPanel.exe" (
        start "" "dist\QuestPanel\QuestPanel.exe"
        goto :eof
    )
    echo   No packaged build found. Build it with: pyinstaller QuestPanel.spec
    echo   Falling back to running from source.
    echo.
)

rem --- Locate an interpreter ------------------------------------------
rem  py.exe is the Windows launcher and is the most reliable; fall back
rem  to whatever "python" resolves to on PATH.
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo.
    echo   Python was not found.
    echo.
    echo   Install Python 3.10 or newer from https://python.org/downloads
    echo   and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

rem --- Dependencies ---------------------------------------------------
if defined REINSTALL goto install
%PY% -c "import PySide6" >nul 2>&1
if not errorlevel 1 goto run

:install
echo.
echo   Installing dependencies (first run only, this takes a minute)...
echo.
%PY% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo   Dependency install failed. Try running:
    echo       %PY% -m pip install PySide6
    echo.
    pause
    exit /b 1
)

:run
if defined CONSOLE (
    echo   Starting QuestPanel...
    %PY% main.py
    echo.
    echo   QuestPanel exited with code %errorlevel%.
    pause
    exit /b %errorlevel%
)

rem Silent launch. pythonw.exe has no console, so the window this script
rem was started from closes immediately instead of lingering behind the
rem overlay. Errors are captured to build\launch-error.log.
if not exist "build" mkdir "build"

set "PYW="
for /f "delims=" %%I in ('%PY% -c "import sys,os;p=os.path.join(os.path.dirname(sys.executable),'pythonw.exe');print(p if os.path.isfile(p) else '')" 2^>nul') do set "PYW=%%I"

if defined PYW (
    start "" "%PYW%" main.py
) else (
    rem No pythonw available; run minimised so the console stays out of the way.
    start "QuestPanel" /min cmd /c "%PY% main.py 2> build\launch-error.log"
)

exit /b 0
