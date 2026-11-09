# common.ps1 — Các hàm và biến dùng chung cho bộ script Windows của vuon-uom-iot
# Tương thích Windows PowerShell 5.1

$script:RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:ToolsDir = Join-Path $script:RepoRoot "tools"
$script:RuntimeDir = Join-Path $script:RepoRoot "runtime"
$script:LogsDir = Join-Path $script:RepoRoot "logs"

function Get-RepoPath([string]$RelativePath) {
    return [System.IO.Path]::GetFullPath((Join-Path $script:RepoRoot $RelativePath))
}

function Write-Log([string]$Message, [string]$Level = "INFO", [string]$LogFile = "") {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $formatted = "[$timestamp] [$Level] $Message"
    switch ($Level.ToUpper()) {
        "ERROR"   { Write-Host $formatted -ForegroundColor Red }
        "WARN"    { Write-Host $formatted -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $formatted -ForegroundColor Green }
        default   { Write-Host $formatted }
    }
    $targetLog = if ($LogFile) { $LogFile } elseif ($script:CurrentLogFile) { $script:CurrentLogFile } else { "" }
    if ($targetLog) {
        try {
            [System.IO.File]::AppendAllText($targetLog, "$formatted`r`n", [System.Text.Encoding]::UTF8)
        } catch {}
    }
}

function Import-EnvFile([string]$EnvPath = "") {
    if (-not $EnvPath) {
        $EnvPath = Join-Path $script:RepoRoot ".env"
    }
    if (-not (Test-Path $EnvPath)) {
        Write-Log "Không tìm thấy file cấu hình .env tại $EnvPath" "WARN"
        return $false
    }
    Get-Content $EnvPath | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line -split "=", 2
            if ($parts.Count -eq 2) {
                $name = $parts[0].Trim()
                $val = $parts[1].Trim()
                if ($val -match '^"(.*)"(\s*#.*)?$') {
                    $val = $matches[1]
                } elseif ($val -match "^'(.*)'(\s*#.*)?$") {
                    $val = $matches[1]
                } elseif ($val -match '^([^\s#]+)') {
                    $val = $matches[1]
                }
                [System.Environment]::SetEnvironmentVariable($name, $val, "Process")
            }
        }
    }
    return $true
}

function Test-PortListening([int]$Port, [string]$IP = "") {
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($conns) {
            if ($IP) {
                $matched = $conns | Where-Object { $_.LocalAddress -eq $IP -or $_.LocalAddress -eq "0.0.0.0" -or $_.LocalAddress -eq "::" }
                return ($matched -ne $null)
            }
            return $true
        }
    } catch {}
    return $false
}

function Stop-ProcessByPidFile([string]$PidFilePath, [string]$ProcessName = "") {
    if (-not (Test-Path $PidFilePath)) {
        return $false
    }
    $pidStr = (Get-Content $PidFilePath -ErrorAction SilentlyContinue | Out-String).Trim()
    if ($pidStr -match '^\d+$') {
        $procId = [int]$pidStr
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                if (-not $ProcessName -or $proc.ProcessName -like "*$ProcessName*") {
                    Write-Log "Dừng tiến trình $($proc.ProcessName) (PID: $procId)..."
                    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Milliseconds 500
                }
            }
        } catch {
            Write-Log "Lỗi khi dừng tiến trình PID $procId : $_" "WARN"
        }
    }
    Remove-Item -Force $PidFilePath -ErrorAction SilentlyContinue
    return $true
}

# Khởi động tiến trình TÁCH KHỎI cửa sổ hiện tại (đóng cửa sổ / Ctrl+C / đóng terminal của IDE không làm dịch vụ tắt).
# Dùng Win32_Process.Create: tiến trình do WMI tạo, không thuộc console hay job của terminal đang chạy script.
function Start-StandaloneProcess([string]$FilePath, [string]$ArgumentList = "") {
    $logFile = Get-RepoPath "logs/services/start.log"
    $fullCmd = "`"$FilePath`" $ArgumentList".Trim()
    try {
        $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
        $res = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $fullCmd; ProcessStartupInformation = $startup } -ErrorAction Stop
        if ($res.ReturnValue -eq 0) {
            Write-Log "Khởi động tách rời (WMI) PID $($res.ProcessId): $(Split-Path $FilePath -Leaf)" "INFO" $logFile
            return $res.ProcessId
        }
        Write-Log "WMI Create trả về $($res.ReturnValue) cho $(Split-Path $FilePath -Leaf)" "WARN" $logFile
    } catch {
        Write-Log "WMI Create lỗi: $_" "WARN" $logFile
    }
    Write-Log "Dự phòng Start-Process (dịch vụ có thể tắt khi đóng cửa sổ này): $(Split-Path $FilePath -Leaf)" "WARN" $logFile
    $p = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WindowStyle Hidden -PassThru
    return $p.Id
}

function Get-ToolPath([string]$ToolName) {
    switch ($ToolName) {
        "postgres" { return (Join-Path $script:ToolsDir "pgsql\bin\postgres.exe") }
        "pg_ctl"   { return (Join-Path $script:ToolsDir "pgsql\bin\pg_ctl.exe") }
        "initdb"      { return (Join-Path $script:ToolsDir "pgsql\bin\initdb.exe") }
        "pg_isready"  { return (Join-Path $script:ToolsDir "pgsql\bin\pg_isready.exe") }
        "psql"     { return (Join-Path $script:ToolsDir "pgsql\bin\psql.exe") }
        "pg_dump"  { return (Join-Path $script:ToolsDir "pgsql\bin\pg_dump.exe") }
        "mosquitto"       { return (Join-Path $script:ToolsDir "mosquitto\mosquitto.exe") }
        "mosquitto_ctrl"  { return (Join-Path $script:ToolsDir "mosquitto\mosquitto_ctrl.exe") }
        "mosquitto_pub"   { return (Join-Path $script:ToolsDir "mosquitto\mosquitto_pub.exe") }
        "mosquitto_sub"   { return (Join-Path $script:ToolsDir "mosquitto\mosquitto_sub.exe") }
        "uv"              { return (Join-Path $script:ToolsDir "uv\uv.exe") }
        "node"            { return (Join-Path $script:ToolsDir "node\node.exe") }
        "python"          {
            $py = Get-ChildItem -Path (Join-Path $script:ToolsDir "python") -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($py) { return $py.FullName }
            return ""
        }
        default { return "" }
    }
}

# ---------------------------------------------------------------------------
# Bổ sung (Claude, 06/11): gọi Dynamic Security, kiểm tra MQTT, đồng bộ file dynsec
# ---------------------------------------------------------------------------

# Mosquitto 2.0.18 trên Windows ghi cấu hình dynsec ra "<file>.new" rồi đổi tên đè lên file cũ.
# Windows không cho đổi tên đè nên log báo "Error updating dynsec config file: File exists"
# và thay đổi chỉ nằm trong bộ nhớ broker. Hàm này đưa bản .new (mới nhất) về đúng tên.
# Gọi sau MỖI lệnh dynsec, trước khi khởi động broker và sau khi dừng broker.
function Sync-DynsecFile {
    $json = Get-RepoPath "runtime/mosquitto/dynamic-security.json"
    $new = "$json.new"
    if (-not (Test-Path $new)) { return $false }
    if ((Test-Path $json) -and ((Get-Item $new).LastWriteTimeUtc -lt (Get-Item $json).LastWriteTimeUtc)) {
        Remove-Item -Force $new -ErrorAction SilentlyContinue
        return $false
    }
    Copy-Item -Force $new $json
    Remove-Item -Force $new -ErrorAction SilentlyContinue
    return $true
}

# Chạy mosquitto_ctrl dynsec <args>, trả về @{ ExitCode; Output }
function Invoke-Dynsec([string[]]$DynsecArgs) {
    $ctrl = Get-ToolPath "mosquitto_ctrl"
    $base = @("-h", "127.0.0.1", "-p", "1883", "-u", $env:MQTT_DYNSEC_USER, "-P", $env:MQTT_DYNSEC_PASSWORD, "dynsec")
    $out = & $ctrl @base @DynsecArgs 2>&1 | ForEach-Object { "$_" }
    $code = $LASTEXITCODE
    Start-Sleep -Milliseconds 150
    Sync-DynsecFile | Out-Null
    return [PSCustomObject]@{ ExitCode = $code; Output = ($out -join "`n") }
}

# Thử publish MQTT v5 QoS 1. Trả về "OK", "DENIED" (kết nối được nhưng bị từ chối publish),
# "AUTH_FAILED" (không đăng nhập được) hoặc "ERROR".
function Test-MqttPublish([string]$User, [string]$Password, [string]$Topic, [string]$ClientId = "") {
    $pub = Get-ToolPath "mosquitto_pub"
    $a = @("-h", "127.0.0.1", "-p", "1883", "-V", "mqttv5", "-q", "1", "-t", $Topic, "-m", "probe")
    if ($User) { $a += @("-u", $User) }
    if ($Password) { $a += @("-P", $Password) }
    if ($ClientId) { $a += @("-i", $ClientId) }
    $out = (& $pub @a 2>&1 | ForEach-Object { "$_" }) -join " "
    $code = $LASTEXITCODE
    if ($out -match "(?i)not authori[sz]ed|bad user name|Connection Refused") {
        if ($out -match "(?i)publish") { return "DENIED" }
        return "AUTH_FAILED"
    }
    if ($code -eq 0) { return "OK" }
    return "ERROR"
}

# Thử subscribe MQTT v5. Trả về "OK", "DENIED", "AUTH_FAILED" hoặc "ERROR".
# Không dùng -W của mosquitto_sub: trên Windows tùy chọn này không có tác dụng (dựa vào SIGALRM),
# mosquitto_sub sẽ chạy mãi. Thay vào đó: chạy nền, chờ 3 giây, còn sống nghĩa là đã subscribe được.
function Test-MqttSubscribe([string]$User, [string]$Password, [string]$Topic) {
    $sub = Get-ToolPath "mosquitto_sub"
    $a = "-h 127.0.0.1 -p 1883 -V mqttv5 -t `"$Topic`""
    if ($User) { $a += " -u `"$User`"" }
    if ($Password) { $a += " -P `"$Password`"" }
    $o = [System.IO.Path]::GetTempFileName()
    $e = [System.IO.Path]::GetTempFileName()
    $p = Start-Process -FilePath $sub -ArgumentList $a -WindowStyle Hidden -PassThru -RedirectStandardOutput $o -RedirectStandardError $e
    for ($i = 0; $i -lt 6 -and -not $p.HasExited; $i++) { Start-Sleep -Milliseconds 500 }
    $alive = -not $p.HasExited
    if ($alive) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 200 }
    $out = ((Get-Content $o -ErrorAction SilentlyContinue) + (Get-Content $e -ErrorAction SilentlyContinue)) -join " "
    Remove-Item -Force $o, $e -ErrorAction SilentlyContinue
    if ($out -match "(?i)subscription requests were denied|subscription.*denied") { return "DENIED" }
    if ($out -match "(?i)not authori[sz]ed|bad user name|Connection Refused") { return "AUTH_FAILED" }
    if ($alive) { return "OK" }
    return "ERROR"
}

# Tạo môi trường Python (.venv) cho một dịch vụ bằng uv + Python trong tools/, cài requirements khi file thay đổi.
function Ensure-Venv([string]$ServiceDir) {
    $venv = Join-Path $ServiceDir ".venv"
    $py = Join-Path $venv "Scripts\python.exe"
    $req = Join-Path $ServiceDir "requirements.txt"
    $stamp = Join-Path $venv ".req-hash"
    $uv = Get-ToolPath "uv"
    $env:UV_CACHE_DIR = Get-RepoPath "tools/uv/.cache"
    $env:UV_PYTHON_INSTALL_DIR = Get-RepoPath "tools/python"
    if (-not (Test-Path $py)) {
        Write-Log "Tạo môi trường Python: $venv"
        & $uv venv $venv --python (Get-ToolPath "python") | Out-Host
    }
    $hash = (Get-FileHash $req -Algorithm SHA256).Hash
    $old = if (Test-Path $stamp) { (Get-Content $stamp -Raw).Trim() } else { "" }
    if ($hash -ne $old) {
        Write-Log "Cài thư viện từ $req ..."
        & $uv pip install --python $py -r $req | Out-Host
        if ($LASTEXITCODE -ne 0) { Write-Log "Cài thư viện thất bại" "ERROR"; return $null }
        [System.IO.File]::WriteAllText($stamp, $hash)
    }
    return $py
}

# Tìm tiến trình theo một đoạn trong dòng lệnh (ví dụ "uvicorn app.main:app")
function Get-ProcessByCommandLine([string]$Pattern) {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$Pattern*" }
}
