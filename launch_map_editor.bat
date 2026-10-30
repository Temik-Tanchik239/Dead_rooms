@echo off
setlocal
cd /d "%~dp0"
title DEAD ROOMS - Редактор карт

 echo ========================================
 echo   DEAD ROOMS - запуск редактора карт
 echo ========================================
 echo.

rem Prefer uv so the editor uses the same project environment as the game.
where uv >nul 2>nul
if not errorlevel 1 (
  echo Запуск редактора через uv...
  uv run python map_editor.py
  if not errorlevel 1 exit /b 0
  echo.
  echo Не удалось запустить через uv. Пробуем системный Python...
)

where python >nul 2>nul
if not errorlevel 1 (
  python map_editor.py
  if not errorlevel 1 exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 map_editor.py
  if not errorlevel 1 exit /b 0
)

echo.
echo ОШИБКА: Python не найден или редактор завершился с ошибкой.
echo Установите Python 3.10+ с python.org и включите Add Python to PATH.
echo Если проект использует uv, установите его: https://docs.astral.sh/uv/
echo.
pause
exit /b 1
