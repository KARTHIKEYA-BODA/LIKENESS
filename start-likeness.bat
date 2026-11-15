@echo off
setlocal
title Likeness local website
cd /d "%~dp0"

echo.
echo Starting Likeness at http://localhost:5173 ...
echo Keep this window open while using Google sign-in.
echo.
py -3 -m http.server 5173 --directory "%~dp0"

echo.
echo The Likeness server stopped. Press any key to close this window.
pause >nul
