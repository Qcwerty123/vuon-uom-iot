# reset-db.ps1 — Xóa CSDL ứng dụng và tạo lại từ database/init (sao lưu trước khi xóa)
# Lưu ý: thiết bị vẫn giữ config_version cũ trong NVS — đặc tả §9.3.
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param([switch]$Yes)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
$script:CurrentLogFile = Get-RepoPath "logs/services/setup.log"
Import-EnvFile | Out-Null

if (-not $Yes) {
    $ans = Read-Host "Xóa toàn bộ dữ liệu CSDL '$($env:POSTGRES_DB)'? Gõ XOA để xác nhận"
    if ($ans -ne "XOA") { Write-Log "Đã hủy." "WARN"; exit 1 }
}

& (Join-Path $scriptDir "start.ps1") | Out-Null
& (Join-Path $scriptDir "backup.ps1")

$dbPort = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$env:PGPASSWORD = $env:PG_SUPERUSER_PASSWORD
& (Get-ToolPath "psql") -h 127.0.0.1 -p $dbPort -U postgres -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS `"$($env:POSTGRES_DB)`" WITH (FORCE);"
$code = $LASTEXITCODE
$env:PGPASSWORD = $null
if ($code -ne 0) { Write-Log "Xóa CSDL thất bại" "ERROR"; exit 1 }
Write-Log "Đã xóa CSDL $($env:POSTGRES_DB). Tạo lại bằng setup.ps1..." "WARN"

& (Join-Path $scriptDir "stop.ps1") | Out-Null
& (Join-Path $scriptDir "setup.ps1")
