# Windows 11 Start Script for Autonomous Voice Browser
# Launches the Native Desktop Floating Orb Overlay over Google Chrome
$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Starting Autonomous Voice Browser (Native Floating Orb)   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

python scripts/desktop_overlay.py
