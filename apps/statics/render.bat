@echo off
REM Re-render the static promo screens to 1080x1920 PNGs after editing the HTML.
REM Usage: double-click, or run from a terminal in this folder.

setlocal
set CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"

set HERE=%~dp0

%CHROME% --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 ^
    --window-size=1080,1920 --virtual-time-budget=6000 ^
    --screenshot="%HERE%open-day-2026.png" "file:///%HERE:\=/%openDay.html"

%CHROME% --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 ^
    --window-size=1080,1920 --virtual-time-budget=6000 ^
    --screenshot="%HERE%youth-open-day-2026.png" "file:///%HERE:\=/%youthOpenDay.html"

echo Done - PNGs written to %HERE%
pause
