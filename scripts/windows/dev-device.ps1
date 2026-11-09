# dev-device.ps1 — Quản lý tài khoản thiết bị trên Mosquitto (Dynamic Security) khi chưa có backend
# Đặc tả: docs/dac-ta-he-thong.md §8.8 · WP-00 §3.6 · Tương thích Windows PowerShell 5.1
#   dev-device.ps1 create  -Code ctl-0001 [-Garden g01]   # in secret MỘT lần
#   dev-device.ps1 disable|enable|delete -Code ctl-0001
#   dev-device.ps1 list

[CmdletBinding()]
param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet("create", "disable", "enable", "delete", "list")]
    [string]$Action,
    [Parameter(Position=1)] [string]$Code,
    [Parameter()] [string]$Garden = "g01",
    [Parameter()] [string]$SecretOutFile = ""   # chỉ dùng cho script kiểm thử: ghi secret ra file thay vì in
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
$script:CurrentLogFile = Get-RepoPath "logs/services/dev-device.log"
Import-EnvFile | Out-Null

if (-not (Test-PortListening 1883)) {
    Write-Log "Mosquitto chưa chạy trên cổng 1883. Chạy scripts\windows\start.ps1 trước." "ERROR"
    exit 1
}
if ($Action -ne "list" -and [string]::IsNullOrWhiteSpace($Code)) {
    Write-Log "Thiếu tham số -Code <device_code>" "ERROR"
    exit 1
}
if ($Code -and $Code -notmatch '^[a-z]{3,4}-\d{4}$') {
    Write-Log "device_code phải có dạng ctl-0001, cam-0001, test-0001" "ERROR"
    exit 1
}

function Must([string[]]$DynsecArgs, [string]$What) {
    $r = Invoke-Dynsec $DynsecArgs
    if ($r.ExitCode -ne 0 -or $r.Output -match "(?i)error|fail") {
        Write-Log "$What thất bại: $($r.Output)" "ERROR"
        exit 1
    }
}

switch ($Action.ToLower()) {
    "create" {
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $bytes = New-Object byte[] 32
        $rng.GetBytes($bytes)
        $secret = [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_').TrimEnd('=')

        Must @("createClient", $Code, "-p", $secret) "Tạo client $Code (có thể đã tồn tại)"
        Must @("createRole", $Code) "Tạo role $Code"
        $base = "nursery/$Garden/$Code"
        foreach ($k in @("telemetry", "status", "event", "ack")) {
            Must @("addRoleACL", $Code, "publishClientSend", "$base/$k", "allow") "ACL publish $k"
        }
        foreach ($k in @("command", "config")) {
            Must @("addRoleACL", $Code, "subscribeLiteral", "$base/$k", "allow") "ACL subscribe $k"
            Must @("addRoleACL", $Code, "publishClientReceive", "$base/$k", "allow") "ACL receive $k"
        }
        Must @("addClientRole", $Code, $Code) "Gán role cho $Code"
        Write-Log "CREATE $Code (vườn $Garden)" "SUCCESS"

        if ($SecretOutFile) {
            [System.IO.File]::WriteAllText($SecretOutFile, $secret)
        } else {
            Write-Host "==========================================================" -ForegroundColor Cyan
            Write-Host " DEVICE_CODE   : $Code" -ForegroundColor Cyan
            Write-Host " GARDEN_CODE   : $Garden" -ForegroundColor Cyan
            Write-Host " DEVICE_SECRET : $secret" -ForegroundColor Yellow
            Write-Host " Chép secret vào secrets.h ngay. Secret không được lưu ở đâu khác." -ForegroundColor Magenta
            Write-Host "==========================================================" -ForegroundColor Cyan
        }
    }
    "disable" { Must @("disableClient", $Code) "Khóa $Code"; Write-Log "DISABLE $Code" "SUCCESS" }
    "enable"  { Must @("enableClient", $Code) "Mở khóa $Code"; Write-Log "ENABLE $Code" "SUCCESS" }
    "delete"  {
        Must @("deleteClient", $Code) "Xóa client $Code"
        Must @("deleteRole", $Code) "Xóa role $Code"
        Write-Log "DELETE $Code" "SUCCESS"
    }
    "list" {
        $r = Invoke-Dynsec @("listClients")
        Write-Host $r.Output
    }
}
