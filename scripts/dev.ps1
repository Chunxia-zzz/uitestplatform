# 同时启动后端(8000) / 前端(5173) / fixture 静态站(8899)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","app.main:app","--reload","--port","8000" `
  -WorkingDirectory "$root\backend"

Start-Process -FilePath "$root\.venv\Scripts\python.exe" `
  -ArgumentList "$root\scripts\serve_fixtures.py"

Start-Process -FilePath "npm" -ArgumentList "run","dev" -WorkingDirectory "$root\frontend"

Write-Host "后端 http://127.0.0.1:8000/docs"
Write-Host "前端 http://localhost:5173"
Write-Host "fixture http://127.0.0.1:8899/login.html"
