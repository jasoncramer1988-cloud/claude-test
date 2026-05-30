@echo off
REM ============================================================
REM   REAL Bitcoin data backtest  -  $10,000 starting capital
REM   Paper simulation only: no exchange, no keys, no money moved.
REM ============================================================
cd /d "%~dp0"
cls
echo ============================================================
echo    REAL BTC BACKTEST  ($10,000 paper capital, no real money)
echo ============================================================
echo.

set PY=
where py >nul 2>nul && set PY=py
if "%PY%"=="" ( where python >nul 2>nul && set PY=python )

if "%PY%"=="" (
    echo  [!] Python 3 was not found. Install it from:
    echo      https://www.python.org/downloads/   (tick "Add Python to PATH")
    echo.
    goto end
)

%PY% run_real_btc.py --capital 10000 --days 90
echo.
echo  Drawing the equity-curve chart...
%PY% plot_equity.py runs\real_btc
if exist runs\real_btc\equity_curve.png start "" runs\real_btc\equity_curve.png

:end
echo.
echo  Press any key to close this window...
pause >nul
