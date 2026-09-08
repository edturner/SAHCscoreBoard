@echo off
REM Open the static promo screens in edit mode.
REM
REM Serves the repo over http://localhost:8123 so the browser is allowed to
REM save straight back over the .html files. Click any text, type, hit Save,
REM then run render.bat to make the PNGs.
REM
REM Close this window when you are done editing.

setlocal
cd /d "%~dp0..\.."

start "" http://localhost:8123/apps/statics/openDay.html?edit
start "" http://localhost:8123/apps/statics/youthOpenDay.html?edit

echo.
echo   Edit mode running at http://localhost:8123/apps/statics/
echo   Close this window when you have finished editing.
echo.

py -m http.server 8123
