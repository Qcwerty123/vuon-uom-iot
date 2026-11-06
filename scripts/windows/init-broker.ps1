# init-broker.ps1 — Khởi tạo cấu hình và Dynamic Security cho Mosquitto trên Windows
# Thay thế cho deployment/mosquitto/init-dynsec.sh
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")

Write-Log "=== Khởi tạo cấu hình Mosquitto Broker (init-broker.ps1) ==="

# 1. Kiểm tra .env
if (-not (Import-EnvFile)) {
    Write-Log "Không tải được file .env" "ERROR"
    exit 1
}

$mosqExe = Get-ToolPath "mosquitto"
$mosqCtrlExe = Get-ToolPath "mosquitto_ctrl"
if (-not (Test-Path $mosqExe) -or -not (Test-Path $mosqCtrlExe)) {
    Write-Log "Thiếu mosquitto hoặc mosquitto_ctrl trong tools/mosquitto" "ERROR"
    exit 1
}

# 2. Sinh runtime/mosquitto/mosquitto.conf từ mẫu deployment/mosquitto/mosquitto.windows.conf
$tplPath = Get-RepoPath "deployment/mosquitto/mosquitto.windows.conf"
if (-not (Test-Path $tplPath)) {
    Write-Log "Không tìm thấy file mẫu cấu hình $tplPath" "ERROR"
    exit 1
}

$runtimeMosqDir = Get-RepoPath "runtime/mosquitto"
if (-not (Test-Path $runtimeMosqDir)) {
    New-Item -ItemType Directory -Force -Path $runtimeMosqDir | Out-Null
}

$repoSlash = $script:RepoRoot.Replace('\', '/')
$tplContent = [System.IO.File]::ReadAllText($tplPath, [System.Text.Encoding]::UTF8)
$confContent = $tplContent.Replace("{{REPO_ROOT}}", $repoSlash)

$confPath = Join-Path $runtimeMosqDir "mosquitto.conf"
[System.IO.File]::WriteAllText($confPath, $confContent, (New-Object System.Text.UTF8Encoding($false)))
Write-Log "Đã sinh cấu hình: $confPath" "SUCCESS"

# 3. Khởi tạo dynamic-security.json nếu chưa có
$dynSecPath = Join-Path $runtimeMosqDir "dynamic-security.json"
$needDynsecSetup = -not (Test-Path $dynSecPath)

if (-not $needDynsecSetup) {
    Write-Log "Đã có file dynamic-security.json — bỏ qua bước tạo tài khoản admin." "INFO"
} else {
    Write-Log "Khởi tạo dynamic-security.json với tài khoản quản trị: $($env:MQTT_DYNSEC_USER)..."
    & $mosqCtrlExe dynsec init $dynSecPath $env:MQTT_DYNSEC_USER $env:MQTT_DYNSEC_PASSWORD | Out-Null
    if (-not (Test-Path $dynSecPath)) {
        Write-Log "Khởi tạo dynamic-security.json thất bại!" "ERROR"
        exit 1
    }
    Write-Log "Tạo dynamic-security.json thành công." "SUCCESS"
}

# 4. Đảm bảo tài khoản backend + role (chạy cả khi dynamic-security.json đã có, để sửa lần khởi tạo dở dang)
$wasRunning = Test-PortListening 1883
$mosqProc = $null
if (-not $wasRunning) {
    Sync-DynsecFile | Out-Null
    Write-Log "Khởi động Mosquitto tạm thời để kiểm tra tài khoản backend..."
    $mosqProc = Start-Process -FilePath $mosqExe -ArgumentList @("-c", "`"$confPath`"") -WindowStyle Hidden -PassThru
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-PortListening 1883) { $ready = $true; break }
    }
    if (-not $ready) {
        Write-Log "Mosquitto không khởi động được trên cổng 1883. Xem logs/services/mosquitto.log" "ERROR"
        exit 1
    }
}

try {
    $list = (Invoke-Dynsec @("listClients")).Output
    if ($list -match "(?m)^\s*$([regex]::Escape($env:MQTT_BACKEND_USER))\s*$") {
        Write-Log "Tài khoản $($env:MQTT_BACKEND_USER) đã có trên broker." "INFO"
    } else {
        Write-Log "Tạo tài khoản backend $($env:MQTT_BACKEND_USER) và role theo đặc tả §8.8..."
        Invoke-Dynsec @("createClient", $env:MQTT_BACKEND_USER, "-p", $env:MQTT_BACKEND_PASSWORD) | Out-Null
        Invoke-Dynsec @("createRole", "backend") | Out-Null
        foreach ($t in @("telemetry", "status", "event", "ack")) {
            Invoke-Dynsec @("addRoleACL", "backend", "subscribePattern", "nursery/+/+/$t", "allow") | Out-Null
        }
        Invoke-Dynsec @("addRoleACL", "backend", "publishClientReceive", "nursery/#", "allow") | Out-Null
        foreach ($t in @("command", "config")) {
            Invoke-Dynsec @("addRoleACL", "backend", "publishClientSend", "nursery/+/+/$t", "allow") | Out-Null
        }
        Invoke-Dynsec @("addClientRole", $env:MQTT_BACKEND_USER, "backend") | Out-Null
        Write-Log "Đã tạo tài khoản backend." "SUCCESS"
    }
    $probe = Test-MqttPublish $env:MQTT_BACKEND_USER $env:MQTT_BACKEND_PASSWORD "nursery/g00/probe-0000/command" "init-probe"
    if ($probe -eq "OK") { Write-Log "Kiểm tra đăng nhập backend: OK" "SUCCESS" } else { Write-Log "Kiểm tra đăng nhập backend: $probe" "ERROR" }
} finally {
    if ($mosqProc -and -not $mosqProc.HasExited) {
        Write-Log "Dừng Mosquitto tạm thời..."
        Stop-Process -Id $mosqProc.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    Sync-DynsecFile | Out-Null
}

Write-Log "=== Hoàn tất init-broker.ps1 ===" "SUCCESS"
