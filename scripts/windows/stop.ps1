# stop.ps1 — Dừng các dịch vụ theo thứ tự ngược lại
# Thứ tự: Backend -> AI service -> Mosquitto -> PostgreSQL
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param([switch]$OnlyBroker)   # -OnlyBroker: chỉ dừng Mosquitto

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")

Write-Log "=== Dừng các dịch vụ VuonUom (stop.ps1) ==="

Import-EnvFile | Out-Null
$pidsDir = Get-RepoPath "runtime/pids"
$pgDataDir = Get-RepoPath "runtime/pgdata"

# 1. Backend & AI service
if (-not $OnlyBroker) {
$be = Get-ProcessByCommandLine "uvicorn app.main:app"
foreach ($p in @($be)) {
    if ($p) { Write-Log "Dừng backend (PID $($p.ProcessId))..."; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
}

$aiPidFile = Join-Path $pidsDir "ai.pid"
if (Test-Path $aiPidFile) {
    Stop-ProcessByPidFile $aiPidFile "python"
}

}

# 2. Mosquitto
$mosqPidFile = Join-Path $pidsDir "mosquitto.pid"
if (Test-Path $mosqPidFile) {
    Stop-ProcessByPidFile $mosqPidFile "mosquitto"
} else {
    # Nếu không có PID file nhưng vẫn đang chạy
    $mosqProcs = Get-Process -Name "mosquitto" -ErrorAction SilentlyContinue
    if ($mosqProcs) {
        Write-Log "Dừng các tiến trình Mosquitto đang chạy..."
        $mosqProcs | Stop-Process -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 300
if (Sync-DynsecFile) { Write-Log "Đã đồng bộ dynamic-security.json từ bản .new" "INFO" }
Write-Log "Mosquitto: Đã dừng." "SUCCESS"
if ($OnlyBroker) { exit 0 }

# 3. PostgreSQL
$pgCtl = Get-ToolPath "pg_ctl"
if (Test-Path $pgDataDir) {
    Write-Log "PostgreSQL: Đang dừng nhẹ nhàng (fast shutdown)..."
    Start-Process -FilePath $pgCtl -ArgumentList @("-D", $pgDataDir, "-w", "stop", "-m", "fast") -WindowStyle Hidden -Wait
    $pgPidFile = Join-Path $pidsDir "postgres.pid"
    if (Test-Path $pgPidFile) {
        Remove-Item -Force $pgPidFile -ErrorAction SilentlyContinue
    }
    Write-Log "PostgreSQL: Đã dừng." "SUCCESS"
}

Write-Log "=== Hoàn tất stop.ps1 ===" "SUCCESS"

