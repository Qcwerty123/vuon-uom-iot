# test-backend.ps1 — Kiểm thử đầu-cuối backend. Backend phải đang chạy (start.ps1).
#   .\scripts\windows\test-backend.ps1           # WP-02 (đăng nhập, thiết bị, ingest, WebSocket)
#   .\scripts\windows\test-backend.ps1 -Wp 03    # WP-03 (lệnh, cấu hình, offline, cảnh báo, người dùng, audit)
#   .\scripts\windows\test-backend.ps1 -Wp 07    # WP-07 (upload ảnh, AI stub, chẩn đoán, AI_LEAF, gardens/zones)
#   .\scripts\windows\test-backend.ps1 -Wp 08    # WP-08 (đèn chiếu sáng Node 1, cấu hình camera, diagnoses.lamp_on)
#     -Wp 07 tạm dừng AI service thật, test tự bật AI_MODE=stub ở 127.0.0.1:8001, xong thì bật lại AI thật (start.ps1).
# Tương thích Windows PowerShell 5.1
param([string]$Wp = "02")
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
$py = Ensure-Venv (Get-RepoPath "backend/api")
if (-not $py) { exit 1 }
$env:PYTHONIOENCODING = "utf-8"
if ($Wp -eq "07") {
    $aiPy = Ensure-Venv (Get-RepoPath "backend/ai-service")
    if (-not $aiPy) { exit 1 }
    $env:WP07_AI_PY = $aiPy
    & (Join-Path $scriptDir "stop.ps1") -OnlyAi | Out-Null
}
& $py (Get-RepoPath "tests/api/smoke_wp$Wp.py")
$code = $LASTEXITCODE
if ($Wp -eq "07") {
    Write-Log "Bật lại AI service thật (start.ps1)..."
    & (Join-Path $scriptDir "start.ps1") *>&1 | Select-String -Pattern "AI service|ERROR" | ForEach-Object { Write-Host $_ }
}
exit $code
