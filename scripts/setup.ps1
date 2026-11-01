# 一键初始化：venv + Python 依赖 + Chromium + 前端依赖
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv")) {
    Write-Host "==> 创建虚拟环境 .venv"
    python -m venv .venv
}

Write-Host "==> 安装后端依赖"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt

Write-Host "==> 安装 Playwright Chromium（验证器/执行器需要）"
& .\.venv\Scripts\python.exe -m playwright install chromium

Write-Host "==> 安装前端依赖"
Push-Location frontend
npm install
Pop-Location

Write-Host ""
Write-Host "完成。下一步："
Write-Host "  cd backend; ..\.venv\Scripts\python.exe -m app.cli seed-demo"
Write-Host "  .\scripts\dev.ps1"
