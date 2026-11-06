# verify.ps1 — Kiểm tra nghiệm thu WP-00 (tiêu chí docs/tasks/WP-00 §4). Không đổi dữ liệu thật.
# Kết quả: logs/tests/verify-<ngày-giờ>.txt · Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param([switch]$SkipSt3)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
Import-EnvFile | Out-Null
$script:CurrentLogFile = Get-RepoPath ("logs/tests/verify-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")
$fail = 0
function Check([string]$Name, [bool]$Pass, [string]$Detail = "") {
    if (-not $Pass) { $script:fail++ }
    Write-Log ("{0} {1} {2}" -f $(if ($Pass) { "PASS" } else { "FAIL" }), $Name, $Detail) $(if ($Pass) { "SUCCESS" } else { "ERROR" })
}

Write-Log "=== verify.ps1 ==="
foreach ($t in @("psql", "pg_ctl", "pg_dump", "mosquitto", "mosquitto_ctrl", "mosquitto_pub", "mosquitto_sub", "uv", "node")) {
    Check "Cong cu $t" (Test-Path (Get-ToolPath $t))
}

& (Join-Path $scriptDir "start.ps1") *> $null
$dbPort = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }

# CSDL
$env:PGPASSWORD = $env:POSTGRES_PASSWORD
$rows = & (Get-ToolPath "psql") -h 127.0.0.1 -p $dbPort -U $env:POSTGRES_USER -d $env:POSTGRES_DB -t -A -F "," -c "select device_code, status from devices order by device_code;" 2>&1
$env:PGPASSWORD = $null
$rowsText = ($rows | ForEach-Object { "$_".Trim() } | Where-Object { $_ }) -join " ; "
Check "CSDL: 2 thiet bi REGISTERED" ($rowsText -eq "cam-0001,REGISTERED ; ctl-0001,REGISTERED") $rowsText
$listen = Get-NetTCPConnection -LocalPort ([int]$dbPort) -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty LocalAddress -Unique
Check "CSDL chi nghe 127.0.0.1" ((@($listen) -join ",") -eq "127.0.0.1") (@($listen) -join ",")

# Broker
Check "Broker nghe cong 1883" (Test-PortListening 1883)
Check "An danh bi tu choi" ((Test-MqttPublish "" "" "nursery/g01/ctl-0001/telemetry" "verify-anon") -eq "AUTH_FAILED")
Check "Backend subscribe telemetry duoc" ((Test-MqttSubscribe $env:MQTT_BACKEND_USER $env:MQTT_BACKEND_PASSWORD "nursery/+/+/telemetry") -eq "OK")
Check "Backend publish telemetry bi tu choi" ((Test-MqttPublish $env:MQTT_BACKEND_USER $env:MQTT_BACKEND_PASSWORD "nursery/g01/ctl-0001/telemetry" "verify-be1") -eq "DENIED")
Check "Backend publish command duoc" ((Test-MqttPublish $env:MQTT_BACKEND_USER $env:MQTT_BACKEND_PASSWORD "nursery/g00/probe-0000/command" "verify-be2") -eq "OK")
Check "Khong con file dynamic-security.json.new" (-not (Test-Path (Get-RepoPath "runtime/mosquitto/dynamic-security.json.new")))

# ST3 / ST4 / lưu dynsec
if (-not $SkipSt3) {
    & (Get-RepoPath "tests/security/st3-dynsec-windows.ps1") *> $null
    Check "ST3/ST4/C18 (chi tiet: logs/tests/st3-dynsec-windows.txt)" ($LASTEXITCODE -eq 0)
}

# Dừng rồi chạy lại: dữ liệu còn nguyên
& (Join-Path $scriptDir "stop.ps1") *> $null
Check "stop.ps1 dung sach" (-not (Test-PortListening ([int]$dbPort)) -and -not (Test-PortListening 1883))
& (Join-Path $scriptDir "start.ps1") *> $null
$env:PGPASSWORD = $env:POSTGRES_PASSWORD
$n = (& (Get-ToolPath "psql") -h 127.0.0.1 -p $dbPort -U $env:POSTGRES_USER -d $env:POSTGRES_DB -t -A -c "select count(*) from devices;" 2>&1 | Out-String).Trim()
$env:PGPASSWORD = $null
Check "Chay lai start.ps1: du lieu con nguyen" ($n -eq "2") $n

# Git
Push-Location $script:RepoRoot
$leak = git status --porcelain 2>$null | Where-Object { $_ -match '^\?\?\s+(tools/|runtime/|logs/|\.env$|DINH-HUONG\.md)' }
Pop-Location
Check "git status khong lo tools/runtime/logs/.env" (-not $leak) (($leak) -join ",")

# Mạng (thông tin, không tính lỗi)
$hot = Get-NetIPAddress -IPAddress "192.168.137.1" -ErrorAction SilentlyContinue
Write-Log ("INFO Mobile Hotspot 192.168.137.1: " + $(if ($hot) { "dang bat" } else { "chua bat" }))
$fw = Get-NetFirewallRule -Name "VuonUom-*" -ErrorAction SilentlyContinue
Write-Log ("INFO Tuong lua VuonUom-*: " + $(if ($fw) { "$(@($fw).Count) luat" } else { "chua co (chay firewall.ps1 bang quyen Administrator)" }))

if ($fail -eq 0) { Write-Log "=== KET QUA: DAT TAT CA ===" "SUCCESS" } else { Write-Log "=== KET QUA: $fail muc KHONG DAT ===" "ERROR" }
Write-Log "Log: $script:CurrentLogFile"
exit $fail
