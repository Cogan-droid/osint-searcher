@echo off
setlocal
title OSINT Tool Searcher
color 0b

:loop
echo.
echo ============================================================
echo           OSINT BOOKMARK ^& SAVED PAGE SEARCHER
echo ============================================================
echo.
set /p query="Enter search keyword (or 'exit' to quit): "

if /i "%query%"=="exit" goto :eof
if "%query%"=="" goto loop

cls
python "%~dp0osint_searcher.py" "%query%"

echo.
pause
goto loop
