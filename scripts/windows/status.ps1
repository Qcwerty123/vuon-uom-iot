# status.ps1 — Kiểm tra trạng thái hệ thống VuonUom
# In bảng: PostgreSQL, Mosquitto, Backend, AI service, IP Hotspot, Luật tường lửa
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")

Import-EnvFile | Out-Null

$dbPort = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$psql = Get-ToolPath "psql"
$mosqSub = Get-ToolPath "mosquitto_sub"

Write-Host ""
Write-Host "========================== TRẠNG THÁI HỆ THỐNG VUONUOM ==========================" -ForegroundColor Cyan

$statusRows = @()

# 1. PostgreSQL
$pgListening = Test-PortListening ([int]$dbPort)
$pgDetail = "Chưa chạy"
$pgStatus = "DỪNG"
if ($pgListening) {
    try {
        $env:PGPASSWORD = $env:POSTGRES_PASSWORD
        $querySql = "SELECT count(*) FROM devices;"
        $tmpSql = [System.IO.Path]::GetTempFileName()
        [System.IO.File]::WriteAllText($tmpSql, $querySql, [System.Text.Encoding]::UTF8)
        $count = (& $psql -h 127.0.0.1 -p $dbPort -U $env:POSTGRES_USER -d $env:POSTGRES_DB -t -f $tmpSql 2>$null)
        Remove-Item -Force $tmpSql -ErrorAction SilentlyContinue
        if ($count -ne $null -and $count.Trim() -match '^\d+$') {
            $pgDetail = "Cổng $dbPort, DB: $($env:POSTGRES_DB), $($count.Trim()) thiết bị"
            $pgStatus = "OK"
        } else {
            $pgDetail = "Cổng $dbPort đang mở nhưng không truy vấn được bảng devices"
            $pgStatus = "CẢNH BÁO"
        }
    } catch {
        $pgDetail = "Lỗi kết nối CSDL: $_"
        $pgStatus = "LỖI"
    } finally {
        $env:PGPASSWORD = $null
    }
}

$statusRows += [PSCustomObject]@{
    "Thành phần" = "PostgreSQL"
    "Cổng/Địa chỉ" = "127.0.0.1:$dbPort"
    "Trạng thái" = $pgStatus
    "Chi tiết" = $pgDetail
}

# 2. Mosquitto
$mosqListening = Test-PortListening 1883
$mosqDetail = "Chưa chạy"
$mosqStatus = "DỪNG"
if ($mosqListening) {
    # Thử đăng nhập bằng tài khoản backend: publish QoS1 (MQTT v5) vào topic command của thiết bị giả
    $probe = Test-MqttPublish $env:MQTT_BACKEND_USER $env:MQTT_BACKEND_PASSWORD "nursery/g00/probe-0000/command" "status-probe"
    if ($probe -eq "OK") {
        $mosqDetail = "Cổng 1883 (0.0.0.0), đăng nhập backend OK"
        $mosqStatus = "OK"
    } else {
        $mosqDetail = "Cổng 1883 mở nhưng kiểm tra backend trả về $probe"
        $mosqStatus = "CẢNH BÁO"
    }
}

$statusRows += [PSCustomObject]@{
    "Thành phần" = "Mosquitto MQTT"
    "Cổng/Địa chỉ" = "0.0.0.0:1883"
    "Trạng thái" = $mosqStatus
    "Chi tiết" = $mosqDetail
}

# 3. Backend API
$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$backendListening = Test-PortListening ([int]$backendPort)
$statusRows += [PSCustomObject]@{
    "Thành phần" = "Backend API"
    "Cổng/Địa chỉ" = "0.0.0.0:$backendPort"
    "Trạng thái" = if ($backendListening) { "OK" } else { "CHƯA CÓ" }
    "Chi tiết" = if ($backendListening) { "Đang lắng nghe" } else { "Chưa chạy hoặc chưa có code" }
}

# 4. AI Service (gọi /v1/health)
$aiPort = 8001
$aiListening = Test-PortListening $aiPort "127.0.0.1"
$aiStatus = "DỪNG"
$aiDetail = "Chưa chạy (start.ps1, hoặc start.ps1 -NoAi đã bỏ qua)"
if ($aiListening) {
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:$aiPort/v1/health" -TimeoutSec 5
        if ($h.status -eq "ok") {
            $aiStatus = if ($h.mode -eq "stub") { "CẢNH BÁO" } else { "OK" }
            $aiDetail = "model_version=$($h.model_version), mode=$($h.mode)"
            if ($h.mode -eq "stub") { $aiDetail += " (stub, KHÔNG phải mô hình thật)" }
        } else {
            $aiStatus = "CẢNH BÁO"
            $aiDetail = "$($h.status): $($h.reason)"
        }
    } catch {
        $aiStatus = "LỖI"
        $aiDetail = "Cổng mở nhưng /v1/health lỗi: $($_.Exception.Message)"
    }
}
$statusRows += [PSCustomObject]@{
    "Thành phần" = "AI Service"
    "Cổng/Địa chỉ" = "127.0.0.1:$aiPort"
    "Trạng thái" = $aiStatus
    "Chi tiết" = $aiDetail
}

# 5. Mobile Hotspot IP
$hotspotIp = "192.168.137.1"
$hasHotspot = $false
try {
    $ipObj = Get-NetIPAddress -IPAddress $hotspotIp -ErrorAction SilentlyContinue
    if ($ipObj) { $hasHotspot = $true }
} catch {}

$statusRows += [PSCustomObject]@{
    "Thành phần" = "Mobile Hotspot"
    "Cổng/Địa chỉ" = $hotspotIp
    "Trạng thái" = if ($hasHotspot) { "OK" } else { "TẮT" }
    "Chi tiết" = if ($hasHotspot) { "IP 192.168.137.1 đã sẵn sàng" } else { "Cần bật Mobile Hotspot 2.4GHz trong Windows Settings" }
}

# 6. Tường lửa (Firewall)
$fwRules = Get-NetFirewallRule -Name "VuonUom-*" -ErrorAction SilentlyContinue
$fwOk = ($fwRules -and ($fwRules | Where-Object { $_.Enabled -eq "True" }).Count -ge 2)
$statusRows += [PSCustomObject]@{
    "Thành phần" = "Windows Firewall"
    "Cổng/Địa chỉ" = "TCP 1883, 8000"
    "Trạng thái" = if ($fwOk) { "OK" } else { "CHƯA CÓ" }
    "Chi tiết" = if ($fwOk) { "Đã mở inbound 1883, 8000" } else { "Cần chạy: powershell -File scripts\windows\firewall.ps1 (Admin)" }
}

$statusRows | Format-Table -AutoSize
Write-Host "=================================================================================" -ForegroundColor Cyan
Write-Host ""

