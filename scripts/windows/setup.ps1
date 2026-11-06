# setup.ps1 — Khởi tạo môi trường dữ liệu và CSDL PostgreSQL trên Windows
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")

# Ghi log vào logs/services/setup.log
$setupLogPath = Get-RepoPath "logs/services/setup.log"
$script:CurrentLogFile = $setupLogPath

Write-Log "=== Bắt đầu cài đặt hệ thống VuonUom (setup.ps1) ==="

# 1. Kiểm tra tools
$missingTools = @()
foreach ($tool in @("postgres", "initdb", "pg_ctl", "psql", "pg_isready", "mosquitto", "mosquitto_ctrl", "uv")) {
    $tPath = Get-ToolPath $tool
    if (-not $tPath -or -not (Test-Path $tPath)) {
        $missingTools += $tool
    }
}

if ($missingTools.Count -gt 0) {
    Write-Log "Thiếu các công cụ trong thư mục tools/: $($missingTools -join ', ')" "ERROR"
    Write-Log "Vui lòng chạy scripts\windows\get-tools.ps1 trước." "ERROR"
    exit 1
}
Write-Log "Đã có đầy đủ công cụ portable." "SUCCESS"

# 2. Kiểm tra .env
if (-not (Import-EnvFile)) {
    Write-Log "Không tải được file .env. Vui lòng tạo file .env từ .env.example." "ERROR"
    exit 1
}

$requiredVars = @(
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "PG_SUPERUSER_PASSWORD",
    "DB_PORT",
    "MQTT_BACKEND_USER",
    "MQTT_BACKEND_PASSWORD",
    "MQTT_DYNSEC_USER",
    "MQTT_DYNSEC_PASSWORD"
)

$hasInvalid = $false
foreach ($var in $requiredVars) {
    $val = [System.Environment]::GetEnvironmentVariable($var, "Process")
    if ([string]::IsNullOrWhiteSpace($val)) {
        Write-Log "Biến cấu hình $var chưa được định nghĩa trong .env" "ERROR"
        $hasInvalid = $true
    } elseif ($val -eq "change-me") {
        Write-Log "Biến cấu hình $var vẫn mang giá trị mẫu 'change-me' trong .env" "ERROR"
        $hasInvalid = $true
    }
}

if ($hasInvalid) {
    Write-Log "Vui lòng cập nhật các biến trên trong .env rồi chạy lại." "ERROR"
    exit 1
}
Write-Log "Kiểm tra file .env hợp lệ." "SUCCESS"

# 3. Tạo các thư mục runtime/ và logs/
$dirsToCreate = @(
    "runtime/pgdata",
    "runtime/mosquitto",
    "runtime/images",
    "runtime/ai",
    "runtime/backups",
    "runtime/pids",
    "logs/services",
    "logs/firmware",
    "logs/tests",
    "logs/agent"
)

foreach ($rel in $dirsToCreate) {
    $full = Get-RepoPath $rel
    if (-not (Test-Path $full)) {
        New-Item -ItemType Directory -Force -Path $full | Out-Null
    }
}
Write-Log "Đã tạo đầy đủ các thư mục runtime/ và logs/." "SUCCESS"

# 4. Khởi tạo cụm CSDL PostgreSQL nếu runtime/pgdata còn trống
$pgDataDir = Get-RepoPath "runtime/pgdata"
$pgVersionFile = Join-Path $pgDataDir "PG_VERSION"
$dbPort = if ($env:DB_PORT) { $env:DB_PORT } else { "5432" }
$pgConfPath = Join-Path $pgDataDir "postgresql.conf"

if (Test-Path $pgVersionFile) {
    Write-Log "PostgreSQL: Đã có dữ liệu tại runtime/pgdata (PG_VERSION tồn tại) — bỏ qua initdb." "INFO"
    # Đồng bộ port trong postgresql.conf theo .env nếu có thay đổi
    if (Test-Path $pgConfPath) {
        $confText = [System.IO.File]::ReadAllText($pgConfPath, [System.Text.Encoding]::UTF8)
        if ($confText -match '(?m)^port\s*=\s*\d+') {
            $confText = [System.Text.RegularExpressions.Regex]::Replace($confText, '(?m)^port\s*=\s*\d+', "port = $dbPort")
            [System.IO.File]::WriteAllText($pgConfPath, $confText, (New-Object System.Text.UTF8Encoding($false)))
        } else {
            [System.IO.File]::AppendAllText($pgConfPath, "`r`nport = $dbPort`r`n", (New-Object System.Text.UTF8Encoding($false)))
        }
    }
} else {
    Write-Log "PostgreSQL: Thư mục runtime/pgdata trống. Tiến hành initdb..."
    $tmpPwFile = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tmpPwFile, $env:PG_SUPERUSER_PASSWORD, [System.Text.Encoding]::ASCII)
        
        $initdbArgs = @(
            "-D", $pgDataDir,
            "-U", "postgres",
            "-A", "scram-sha-256",
            "-E", "UTF8",
            "--locale=C",
            "--pwfile=$tmpPwFile"
        )
        $proc = Start-Process -FilePath (Get-ToolPath "initdb") -ArgumentList $initdbArgs -Wait -NoNewWindow -PassThru
        if ($proc.ExitCode -ne 0) {
            Write-Log "initdb thất bại với mã lỗi $($proc.ExitCode)" "ERROR"
            exit 1
        }
    } finally {
        if (Test-Path $tmpPwFile) {
            Remove-Item -Force $tmpPwFile -ErrorAction SilentlyContinue
        }
    }

    # Cấu hình postgresql.conf
    $confAppend = @"

# --- Cấu hình bởi vuon-uom-iot setup.ps1 ---
listen_addresses = '127.0.0.1'
port = $dbPort
"@
    [System.IO.File]::AppendAllText($pgConfPath, $confAppend, (New-Object System.Text.UTF8Encoding($false)))
    Write-Log "Đã khởi tạo cụm CSDL PostgreSQL mới tại $pgDataDir" "SUCCESS"
}

# 5. Khởi động tạm thời PostgreSQL để kiểm tra role, database và nạp schema/seed nếu chưa có
Write-Log "PostgreSQL: Khởi động tạm thời cụm dữ liệu để cấu hình..."
$pgLogPath = Get-RepoPath "logs/services/postgresql.log"

# Xóa file pid cũ nếu bị treo từ phiên trước
$postmasterPid = Join-Path $pgDataDir "postmaster.pid"
if (Test-Path $postmasterPid) {
    $oldPid = (Get-Content $postmasterPid | Select-Object -First 1).Trim()
    if ($oldPid -and -not (Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue)) {
        Remove-Item -Force $postmasterPid -ErrorAction SilentlyContinue
    }
}

# Khởi động PostgreSQL nền
$startArgs = @("-D", $pgDataDir, "-l", $pgLogPath, "start")
Start-Process -FilePath (Get-ToolPath "pg_ctl") -ArgumentList $startArgs -WindowStyle Hidden

# Chờ PostgreSQL sẵn sàng bằng pg_isready (tối đa 30s)
Write-Log "Đang chờ PostgreSQL sẵn sàng trên cổng $dbPort..."
$pgIsReady = Get-ToolPath "pg_isready"
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    & $pgIsReady -h 127.0.0.1 -p $dbPort | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Start-Sleep -Seconds 1
}

if (-not $ready) {
    Write-Log "PostgreSQL không sẵn sàng sau 30 giây. Vui lòng kiểm tra $pgLogPath" "ERROR"
    exit 1
}
Write-Log "PostgreSQL đã sẵn sàng trên 127.0.0.1:$dbPort." "SUCCESS"

$tmpSql = [System.IO.Path]::GetTempFileName()
try {
    $env:PGPASSWORD = $env:PG_SUPERUSER_PASSWORD
    $psqlExe = Get-ToolPath "psql"

    # Đảm bảo role ứng dụng tồn tại
    Write-Log "Kiểm tra role ứng dụng $($env:POSTGRES_USER)..."
    $sqlRole = @"
DO `$`$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$($env:POSTGRES_USER)') THEN
        CREATE ROLE "$($env:POSTGRES_USER)" WITH LOGIN PASSWORD '$($env:POSTGRES_PASSWORD)';
    END IF;
END
`$`$;
"@
    [System.IO.File]::WriteAllText($tmpSql, $sqlRole, [System.Text.Encoding]::UTF8)
    $procRole = Start-Process -FilePath $psqlExe -ArgumentList @("-h", "127.0.0.1", "-p", $dbPort, "-U", "postgres", "-d", "postgres", "-f", $tmpSql) -Wait -NoNewWindow -PassThru
    if ($procRole.ExitCode -ne 0) {
        Write-Log "Tạo role $($env:POSTGRES_USER) thất bại." "ERROR"
        exit 1
    }
    Write-Log "Role $($env:POSTGRES_USER): OK" "SUCCESS"

    # Kiểm tra database POSTGRES_DB đã tồn tại chưa
    $sqlCheckDb = "SELECT 1 FROM pg_database WHERE datname = '$($env:POSTGRES_DB)';"
    [System.IO.File]::WriteAllText($tmpSql, $sqlCheckDb, [System.Text.Encoding]::UTF8)
    $res = & $psqlExe -h 127.0.0.1 -p $dbPort -U postgres -d postgres -t -f $tmpSql
    $dbExists = ($res -and $res.Trim() -eq "1")

    if (-not $dbExists) {
        Write-Log "Database $($env:POSTGRES_DB) chưa tồn tại. Tiến hành tạo mới và nạp schema/seed..."
        $sqlCreateDb = "CREATE DATABASE `"$($env:POSTGRES_DB)`" OWNER `"$($env:POSTGRES_USER)`";"
        [System.IO.File]::WriteAllText($tmpSql, $sqlCreateDb, [System.Text.Encoding]::UTF8)
        $procDb = Start-Process -FilePath $psqlExe -ArgumentList @("-h", "127.0.0.1", "-p", $dbPort, "-U", "postgres", "-d", "postgres", "-f", $tmpSql) -Wait -NoNewWindow -PassThru
        if ($procDb.ExitCode -ne 0) {
            Write-Log "Tạo database $($env:POSTGRES_DB) thất bại." "ERROR"
            exit 1
        }
        Write-Log "Database $($env:POSTGRES_DB): Tạo mới thành công." "SUCCESS"

        # Nạp schema và seed BẰNG ROLE ỨNG DỤNG
        Write-Log "Nạp schema 01_schema.sql bằng role $($env:POSTGRES_USER)..."
        $env:PGPASSWORD = $env:POSTGRES_PASSWORD
        $schemaFile = Get-RepoPath "database/init/01_schema.sql"
        $seedFile = Get-RepoPath "database/init/02_seed.sql"

        $procSchema = Start-Process -FilePath $psqlExe -ArgumentList @("-h", "127.0.0.1", "-p", $dbPort, "-U", $env:POSTGRES_USER, "-d", $env:POSTGRES_DB, "-f", $schemaFile) -Wait -NoNewWindow -PassThru
        if ($procSchema.ExitCode -ne 0) {
            Write-Log "Nạp 01_schema.sql thất bại." "ERROR"
            exit 1
        }
        Write-Log "01_schema.sql: Nạp thành công." "SUCCESS"

        Write-Log "Nạp seed 02_seed.sql bằng role $($env:POSTGRES_USER)..."
        $procSeed = Start-Process -FilePath $psqlExe -ArgumentList @("-h", "127.0.0.1", "-p", $dbPort, "-U", $env:POSTGRES_USER, "-d", $env:POSTGRES_DB, "-f", $seedFile) -Wait -NoNewWindow -PassThru
        if ($procSeed.ExitCode -ne 0) {
            Write-Log "Nạp 02_seed.sql thất bại." "ERROR"
            exit 1
        }
        Write-Log "02_seed.sql: Nạp thành công." "SUCCESS"
    } else {
        Write-Log "Database $($env:POSTGRES_DB): Đã tồn tại — bỏ qua nạp schema/seed." "INFO"
    }
} finally {
    $env:PGPASSWORD = $null
    if (Test-Path $tmpSql) {
        Remove-Item -Force $tmpSql -ErrorAction SilentlyContinue
    }
    # 6. Dừng PostgreSQL tạm
    Write-Log "Dừng PostgreSQL tạm thời..."
    Start-Process -FilePath (Get-ToolPath "pg_ctl") -ArgumentList @("-D", $pgDataDir, "-w", "stop", "-m", "fast") -WindowStyle Hidden -Wait
    Start-Sleep -Seconds 1
}

Write-Log "=== Hoàn tất setup.ps1 ===" "SUCCESS"
