# test-backend.ps1 — Kiểm thử đầu-cuối backend (tests/api/smoke_wp02.py). Backend phải đang chạy (start.ps1).
# Tương thích Windows PowerShell 5.1
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
$py = Ensure-Venv (Get-RepoPath "backend/api")
if (-not $py) { exit 1 }
$env:PYTHONIOENCODING = "utf-8"
& $py (Get-RepoPath "tests/api/smoke_wp02.py")
exit $LASTEXITCODE
