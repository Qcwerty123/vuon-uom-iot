# firewall.ps1 — Cấu hình tường lửa Windows cho hệ thống VuonUom
# Yêu cầu quyền Administrator. Mở inbound TCP 1883 (MQTT) và 8000 (Backend / API).
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")

Write-Log "=== Cấu hình Windows Firewall cho VuonUom ==="

$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Log "LỖI: Script này yêu cầu quyền Administrator để cấu hình Windows Firewall." "ERROR"
    Write-Log "Vui lòng mở PowerShell với quyền 'Run as Administrator' và chạy lại:" "WARN"
    Write-Log "    powershell -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`"" "WARN"
    exit 1
}

$rules = @(
    @{ Name = "VuonUom-MQTT-Inbound-1883"; Port = 1883; Description = "Cho phep thiet bi ket noi MQTT broker Mosquitto (cong 1883)" },
    @{ Name = "VuonUom-HTTP-Inbound-8000"; Port = 8000; Description = "Cho phep truy cap Backend API, Web dashboard, va Node 2 upload anh (cong 8000)" }
)

foreach ($r in $rules) {
    $existing = Get-NetFirewallRule -Name $r.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Log "Đã có luật firewall: $($r.Name) — tiến hành cập nhật..."
        Set-NetFirewallRule -Name $r.Name -DisplayName $r.Name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $r.Port -Profile Any -Description $r.Description
        Write-Log "Cập nhật thành công: $($r.Name)" "SUCCESS"
    } else {
        Write-Log "Đang tạo luật firewall mới: $($r.Name)..."
        New-NetFirewallRule -Name $r.Name -DisplayName $r.Name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $r.Port -Profile Any -Description $r.Description | Out-Null
        Write-Log "Tạo mới thành công: $($r.Name)" "SUCCESS"
    }
}

Write-Log "=== Hoàn tất cấu hình Firewall ===" "SUCCESS"

