# test-backend.ps1 — Kiểm thử đầu-cuối backend. Backend phải đang chạy (start.ps1).
#   .\scripts\windows\test-backend.ps1           # WP-02 (đăng nhập, thiết bị, ingest, WebSocket)
#   .\scripts\windows\test-backend.ps1 -Wp 03    # WP-03 (lệnh, cấu hình, offline, cảnh báo, người dùng, audit)
# Tương thích Windows PowerShell 5.1
param([string]$Wp = "02")
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
$py = Ensure-Venv (Get-RepoPath "backend/api")
if (-not $py) { exit 1 }
$env:PYTHONIOENCODING = "utf-8"
& $py (Get-RepoPath "tests/api/smoke_wp$Wp.py")
exit $LASTEXITCODE
