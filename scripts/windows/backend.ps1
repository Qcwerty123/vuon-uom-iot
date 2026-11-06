# backend.ps1 — Chạy backend ở chế độ phát triển (hiện log trên màn hình, tự nạp lại khi sửa code)
# Dừng backend chạy nền trước: .\scripts\windows\stop.ps1 rồi start lại PostgreSQL + broker bằng start.ps1 -NoBackend
# Tương thích Windows PowerShell 5.1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
Import-EnvFile | Out-Null
$backendDir = Get-RepoPath "backend/api"
$py = Ensure-Venv $backendDir
if (-not $py) { exit 1 }
$port = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$env:PYTHONIOENCODING = "utf-8"
& $py -m uvicorn app.main:app --app-dir $backendDir --host 0.0.0.0 --port $port --reload --reload-dir (Join-Path $backendDir "app")
