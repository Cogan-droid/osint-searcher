@echo off
setlocal
title OSINT Smart Searcher
color 0b

:loop
echo.
echo ============================================================
echo           OSINT SMART SEARCHER (v2.0 - Optimized)
echo ============================================================
echo.
set /p query="Enter search keyword (or 'exit' to quit): "

if /i "%query%"=="exit" goto :eof
if "%query%"=="" goto loop

echo.
set /p tools_only="Only show Tools/Software? (y/n): "

cls
if /i "%tools_only%"=="y" (
    python "%~dp0osint_searcher.py" "%query%" --tools-only
) else (
    python "%~dp0osint_searcher.py" "%query%"
)

echo.
pause
goto loop
