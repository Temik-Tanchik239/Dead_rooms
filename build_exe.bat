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

echo.
echo ГОТОВО! Игра собрана в:
echo   "%~dp0dist\DEAD_ROOMS.exe"
echo.
echo EXE включает игровые ресурсы и запускается двойным щелчком.
echo Если рядом с EXE создать папки data и assets, игра будет использовать их вместо встроенных ресурсов.
pause
exit /b 0

:err
echo.
echo СБОРКА НЕ УДАЛАСЬ. Проверьте сообщения выше.
pause
exit /b 1
