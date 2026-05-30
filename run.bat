@echo off
REM ============================================================
REM   Exchange -> MCP -> Claude Code : Paper-Trading Simulator
REM   Double-click this file to run a backtest. No setup needed.
REM ============================================================
cd /d "%~dp0"
cls
echo ============================================================
echo    PAPER-TRADING SIMULATOR  (no real money, all simulated)
echo ============================================================
echo.

REM Find Python: try the 'py' launcher first, then 'python'.
set PY=
where py >nul 2>nul && set PY=py
if "%PY%"=="" ( where python >nul 2>nul && set PY=python )

if "%PY%"=="" (
    echo  [!] Python was not found on this computer.
    echo.
    echo  Please install Python 3 from:  https://www.python.org/downloads/
    echo  During install, TICK the box that says "Add Python to PATH".
    echo  Then double-click this file again.
    echo.
    goto end
)

echo  Using Python:  %PY%
echo  Running 1000 cycles ... this takes about a second.
echo.

%PY% run_sim.py --cycles 1000 --seed 42 --quiet

echo.
echo  Drawing the equity-curve chart...
%PY% plot_equity.py runs\latest

echo.
echo ============================================================
echo  Done. Opening the chart now. Logs are in the  runs\latest  folder.
echo ============================================================
if exist runs\latest\equity_curve.png start "" runs\latest\equity_curve.png

:end
echo.
echo  Press any key to close this window...
pause >nul
