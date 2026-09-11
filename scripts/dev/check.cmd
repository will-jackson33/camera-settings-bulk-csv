@echo off
rem The one route to "checked": the batch checker, ruff, mypy --strict, then the tests. Stops at
rem the first failure. Run before calling anything in this project done.
setlocal
pushd "%~dp0..\.."
call scripts\dev\venv.cmd || goto failed

echo === check_bat ===
.venv\Scripts\python tests\check_bat.py || goto failed
echo === ruff ===
.venv\Scripts\python -m ruff check src tests scripts || goto failed
echo === mypy ===
.venv\Scripts\python -m mypy src scripts || goto failed
echo === pytest ===
.venv\Scripts\python -m pytest -q %* || goto failed

echo.
echo All checks passed.
popd
endlocal & exit /b 0

:failed
echo.
echo CHECK FAILED - see above.
popd
endlocal & exit /b 1
