@echo off
REM Builds DeadRooms.exe with uv (https://docs.astral.sh/uv/)
uv sync || goto :err
uv run pyinstaller --noconfirm --windowed --name DeadRooms main.py || goto :err
xcopy /E /I /Y data dist\DeadRooms\data >nul
xcopy /E /I /Y assets dist\DeadRooms\assets >nul
echo.
echo DONE: dist\DeadRooms\DeadRooms.exe  (keep the "data" folder next to the exe)
pause
exit /b 0
:err
echo BUILD FAILED. Is uv installed? https://docs.astral.sh/uv/
pause
