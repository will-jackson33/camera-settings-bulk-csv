@echo off
rem Makes sure .venv exists inside the project with the pinned dependencies installed, and keeps it
rem hidden: a technician opening this folder sees the two scripts and the README, not the
rem development plumbing. Called by check.cmd; nothing lands on the machine.
rem Python 3.12 is the one prerequisite; when it is missing this names it and stops.
setlocal
pushd "%~dp0..\.."
if exist ".venv\Scripts\python.exe" goto done

echo [venv] No .venv yet - building one inside this folder.
set "PY312=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PY312%" goto create
py -3.12 --version >nul 2>&1
if errorlevel 1 goto missing
set "PY312=py -3.12"

:create
echo [venv] Creating .venv ...
%PY312% -m venv .venv
if errorlevel 1 goto failed
echo [venv] Installing pinned dependencies ...
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -r scripts\dev\requirements.txt -r scripts\dev\requirements-test.txt
if errorlevel 1 goto failed
echo [venv] Ready. Everything lives in .venv - delete the folder and the machine is untouched.

:done
rem The tool caches live under .venv too (pyproject.toml), so hiding it hides all of them.
attrib +h .venv >nul 2>&1
popd
endlocal & exit /b 0

:missing
echo.
echo [venv] MISSING PREREQUISITE: Python 3.12 is not installed.
echo        Install it from https://www.python.org/downloads/ and run this again.
echo.
popd
endlocal & exit /b 1

:failed
echo [venv] FAILED - see the messages above.
popd
endlocal & exit /b 1
