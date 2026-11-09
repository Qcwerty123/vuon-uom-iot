# start.ps1 — Khởi động toàn bộ dịch vụ của hệ thống VuonUom
# Thứ tự: PostgreSQL -> Mosquitto -> AI service -> Backend
# Bỏ qua AI service và Backend nếu chưa có mã nguồn
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param([switch]$NoBackend)   # -NoBackend: không bật backend (khi chạy backend.ps1 để phát triển)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")

Write-Log "=== Khởi động các dịch vụ VuonUom (start.ps1) ==="

if (-not (Import-EnvFile)) {
    Write-Log "Không tìm thấy file .env" "ERROR"
    exit 1
}

$pidsDir = Get-RepoPath "runtime/pids"
if (-not (Test-Path $pidsDir)) {
    New-Item -ItemType Directory -Force -Path $pidsDir | Out-Null
}

$dbPort = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$pgDataDir = Get-RepoPath "runtime/pgdata"
$pgLogPath = Get-RepoPath "logs/services/postgresql.log"
$pgIsReady = Get-ToolPath "pg_isready"

# 1. Khởi động PostgreSQL
if (Test-PortListening ([int]$dbPort)) {
    Write-Log "PostgreSQL: Đang chạy trên cổng $dbPort." "INFO"
} else {
    Write-Log "PostgreSQL: Đang khởi động trên cổng $dbPort..."
    $postmasterPid = Join-Path $pgDataDir "postmaster.pid"
    if (Test-Path $postmasterPid) {
        $oldPid = (Get-Content $postmasterPid | Select-Object -First 1).Trim()
        if ($oldPid -and -not (Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue)) {
            Remove-Item -Force $postmasterPid -ErrorAction SilentlyContinue
        }
    }

    Start-StandaloneProcess (Get-ToolPath "pg_ctl") "-D `"$pgDataDir`" -l `"$pgLogPath`" start" | Out-Null
    
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        & $pgIsReady -h 127.0.0.1 -p $dbPort | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $ready = $true
            break
        }
    }

    if ($ready) {
        if (Test-Path $postmasterPid) {
            $pgPid = (Get-Content $postmasterPid | Select-Object -First 1).Trim()
            [System.IO.File]::WriteAllText((Join-Path $pidsDir "postgres.pid"), $pgPid)
        }
        Write-Log "PostgreSQL: Khởi động thành công (cổng $dbPort)." "SUCCESS"
    } else {
        Write-Log "PostgreSQL: Khởi động thất bại. Kiểm tra log tại $pgLogPath" "ERROR"
    }
}

# 2. Khởi động Mosquitto
$confPath = Get-RepoPath "runtime/mosquitto/mosquitto.conf"
if (-not (Test-Path $confPath)) {
    Write-Log "Chưa có cấu hình runtime/mosquitto/mosquitto.conf. Đang tự động chạy init-broker.ps1..." "WARN"
    & (Join-Path $scriptDir "init-broker.ps1")
}

if (Test-PortListening 1883 "0.0.0.0") {
    Write-Log "Mosquitto: Đang chạy trên cổng 1883." "INFO"
} else {
    Write-Log "Mosquitto: Đang khởi động trên cổng 1883..."
    if (Sync-DynsecFile) { Write-Log "Đã đồng bộ dynamic-security.json từ bản .new" "INFO" }
    $mosqPid = Start-StandaloneProcess (Get-ToolPath "mosquitto") "-c `"$confPath`""
    
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-PortListening 1883 "0.0.0.0") {
            $ready = $true
            break
        }
    }

    if ($ready) {
        [System.IO.File]::WriteAllText((Join-Path $pidsDir "mosquitto.pid"), $mosqPid.ToString())
        Write-Log "Mosquitto: Khởi động thành công (cổng 1883, PID: $mosqPid)." "SUCCESS"
    } else {
        Write-Log "Mosquitto: Khởi động thất bại. Kiểm tra log tại logs/services/mosquitto.log" "ERROR"
    }
}

# 3. AI Service (chưa có code -> bỏ qua và báo)
$aiEntry = Get-RepoPath "backend/ai-service/main.py"
if (Test-Path $aiEntry) {
    Write-Log "AI Service: Đang khởi động..." "INFO"
    # Sẽ bổ sung lệnh khởi động khi backend/ai-service được triển khai
} else {
    Write-Log "AI service: Chưa có mã nguồn (bỏ qua)." "INFO"
}

# 4. Backend (FastAPI, cổng BACKEND_PORT, phục vụ /api, /ws, web tĩnh, /device-api)
$backendDir = Get-RepoPath "backend/api"
$backendPort = if ($env:BACKEND_PORT) { [int]$env:BACKEND_PORT } else { 8000 }
if ($NoBackend) {
    Write-Log "Backend: bỏ qua (-NoBackend)." "INFO"
} elseif (-not (Test-Path (Join-Path $backendDir "app\main.py"))) {
    Write-Log "Backend: Chưa có mã nguồn (bỏ qua)." "INFO"
} elseif (Test-PortListening $backendPort) {
    Write-Log "Backend: Đang chạy trên cổng $backendPort." "INFO"
} else {
    $py = Ensure-Venv $backendDir
    if ($py) {
        $outLog = Get-RepoPath "logs/services/backend-console.log"
        $inner = "`"$py`" -m uvicorn app.main:app --app-dir `"$backendDir`" --host 0.0.0.0 --port $backendPort"
        Start-StandaloneProcess "$env:ComSpec" "/c `"$inner >> `"$outLog`" 2>&1`"" | Out-Null
        $ok = $false
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-PortListening $backendPort) { $ok = $true; break }
        }
        if ($ok) { Write-Log "Backend: Khởi động thành công (cổng $backendPort, /docs để xem API)." "SUCCESS" }
        else { Write-Log "Backend: Không khởi động được. Xem logs/services/backend-console.log và backend.log" "ERROR" }
    }
}

Write-Log "=== Hoàn tất start.ps1 ===" "SUCCESS"
