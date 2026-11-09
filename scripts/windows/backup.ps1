# backup.ps1 — Sao lưu CSDL, tài khoản broker và ảnh vào runtime/backups/<ngày-giờ>/
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
$script:CurrentLogFile = Get-RepoPath "logs/services/backup.log"
Import-EnvFile | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dest = Get-RepoPath "runtime/backups/$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$dbPort = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$ok = $true

if (Test-PortListening ([int]$dbPort)) {
    $env:PGPASSWORD = $env:POSTGRES_PASSWORD
    & (Get-ToolPath "pg_dump") -h 127.0.0.1 -p $dbPort -U $env:POSTGRES_USER -d $env:POSTGRES_DB -F c -f (Join-Path $dest "nursery.dump")
    if ($LASTEXITCODE -ne 0) { $ok = $false; Write-Log "pg_dump thất bại" "ERROR" } else { Write-Log "CSDL: nursery.dump" "SUCCESS" }
    $env:PGPASSWORD = $null
} else {
    $ok = $false
    Write-Log "PostgreSQL chưa chạy — bỏ qua sao lưu CSDL (chạy start.ps1 rồi sao lưu lại)" "WARN"
}

Sync-DynsecFile | Out-Null
$dyn = Get-RepoPath "runtime/mosquitto/dynamic-security.json"
if (Test-Path $dyn) { Copy-Item $dyn $dest; Write-Log "Broker: dynamic-security.json" "SUCCESS" }

$img = Get-RepoPath "runtime/images"
if ((Test-Path $img) -and (Get-ChildItem $img -Recurse -File -ErrorAction SilentlyContinue)) {
    Copy-Item -Recurse $img (Join-Path $dest "images")
    Write-Log "Ảnh: đã chép" "SUCCESS"
}

Write-Log "Sao lưu xong: runtime/backups/$stamp" $(if ($ok) { "SUCCESS" } else { "WARN" })
Write-Log "Khôi phục CSDL: pg_restore -h 127.0.0.1 -p $dbPort -U <POSTGRES_USER> -d <POSTGRES_DB> --clean <thư mục>\nursery.dump"
