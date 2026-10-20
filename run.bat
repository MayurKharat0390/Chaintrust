@echo off
title ChainTrust - AI Agent Reputation Protocol
color 0B

echo =======================================================================
echo          CHAINTRUST ONE-CLICK LAUNCHER
echo =======================================================================
echo.

cd /d "%~dp0"

python run.py

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start ChainTrust. Please verify Python is installed.
    pause
)
