@echo off
setlocal
cd /d "%~dp0"
title DEAD ROOMS - сборка EXE

echo ========================================
echo   DEAD ROOMS - сборка Windows EXE
echo ========================================
echo.
where uv >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: не найден uv.
  echo Установите uv с https://docs.astral.sh/uv/ и запустите этот файл снова.
  pause
  exit /b 1
)

uv sync
if errorlevel 1 goto :err

uv run pyinstaller --noconfirm --clean --onefile --windowed --name DEAD_ROOMS --add-data "data;data" --add-data "assets;assets" main.py
if errorlevel 1 goto :err

rem Копируем редактируемые ресурсы рядом с EXE: замена PNG после сборки сразу видна в игре.
if not exist "dist\assets" mkdir "dist\assets"
xcopy "assets\*" "dist\assets\" /E /I /Y >nul
if errorlevel 1 goto :err
if not exist "dist\data" mkdir "dist\data"
xcopy "data\*" "dist\data\" /E /I /Y >nul
if errorlevel 1 goto :err

echo.
echo ГОТОВО! Запускайте двойным щелчком:
echo   "%~dp0dist\DEAD_ROOMS.exe"
echo.
echo Изменяемые картинки меню лежат в dist\assets\menu\.
echo Можно заменять PNG после сборки — пересобирать EXE не нужно.
pause
exit /b 0

:err
echo.
echo СБОРКА НЕ УДАЛАСЬ. Проверьте сообщения выше.
pause
exit /b 1
