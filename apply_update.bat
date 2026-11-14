@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
title DEAD ROOMS - update
echo ========================================
echo   DEAD ROOMS - installing update v3
echo ========================================
echo.

where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 apply_update.py
if %errorlevel%==0 goto done
if %errorlevel%==3 goto done
echo [py launcher failed, trying other Python]

:try_python
where python >nul 2>nul
if errorlevel 1 goto try_uv
python apply_update.py
if %errorlevel%==0 goto done
if %errorlevel%==3 goto done
echo [python failed, trying uv]

:try_uv
where uv >nul 2>nul
if errorlevel 1 goto nopython
uv run python apply_update.py
if %errorlevel%==0 goto done
if %errorlevel%==3 goto done
goto failed

:nopython
echo ERROR: Python was not found. Install Python 3.10 or newer from python.org and tick "Add Python to PATH",
echo or install uv from https://docs.astral.sh/uv/ and run this file again.
goto failed

:failed
echo.
echo The update was NOT completed. Details are in update_log.txt in the project folder.
pause
exit /b 1

:done
echo.
echo Log saved to update_log.txt
pause
exit /b 0
