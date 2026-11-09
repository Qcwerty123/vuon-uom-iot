# get-tools.ps1 — Tải và giải nén các công cụ portable trên Windows
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")

Write-Log "=== Kiểm tra và tải các công cụ portable (Windows x64) ==="

$UV_VERSION = "0.5.11"
$PYTHON_VERSION = "3.11"
$PG_VERSION = "16.4-1"
$MOSQ_VERSION = "2.0.18"
$NODE_VERSION = "v20.18.0"

New-Item -ItemType Directory -Force -Path $script:ToolsDir | Out-Null
$downloadsDir = Join-Path $script:ToolsDir "_downloads"
New-Item -ItemType Directory -Force -Path $downloadsDir | Out-Null

function Download-FileWithCurlOrWebClient([string]$Url, [string]$OutputFile) {
    if (Test-Path $OutputFile) {
        Write-Log "Đã có sẵn file tải: $OutputFile"
        return $true
    }
    Write-Log "Đang tải $Url -> $OutputFile ..."
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & curl.exe -f -sSL $Url -o $OutputFile
        if ($LASTEXITCODE -eq 0 -and (Test-Path $OutputFile)) {
            return $true
        }
    }
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        $wc = New-Object System.Net.WebClient
        $wc.DownloadFile($Url, $OutputFile)
        return (Test-Path $OutputFile)
    } catch {
        Write-Log "Lỗi khi tải $Url : $_" "ERROR"
        return $false
    }
}

# 1. uv
$uvExe = Join-Path $script:ToolsDir "uv\uv.exe"
if (Test-Path $uvExe) {
    Write-Log "uv: Đã tồn tại tại $uvExe"
} else {
    Write-Log "uv: Đang cài đặt phiên bản $UV_VERSION..."
    $uvZip = Join-Path $downloadsDir "uv-$UV_VERSION.zip"
    $uvUrl = "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-pc-windows-msvc.zip"
    if (Download-FileWithCurlOrWebClient $uvUrl $uvZip) {
        $uvDir = Join-Path $script:ToolsDir "uv"
        New-Item -ItemType Directory -Force -Path $uvDir | Out-Null
        Expand-Archive -Path $uvZip -DestinationPath $uvDir -Force
        Remove-Item -Force $uvZip -ErrorAction SilentlyContinue
        Write-Log "uv: Cài đặt thành công." "SUCCESS"
    } else {
        Write-Log "uv: Tải thất bại. Vui lòng tải thủ công từ $uvUrl và đặt vào $uvZip" "ERROR"
    }
}

# 2. Python 3.11 qua uv
$pythonDir = Join-Path $script:ToolsDir "python"
$pyExe = Get-ToolPath "python"
if ($pyExe -and (Test-Path $pyExe)) {
    Write-Log "Python 3.11: Đã tồn tại tại $pyExe"
} else {
    Write-Log "Python: Đang cài đặt CPython $PYTHON_VERSION qua uv..."
    $env:UV_PYTHON_INSTALL_DIR = $pythonDir
    $env:UV_CACHE_DIR = Join-Path $script:ToolsDir "uv\.cache"
    & (Get-ToolPath "uv") python install $PYTHON_VERSION
    $pyExe = Get-ToolPath "python"
    if ($pyExe -and (Test-Path $pyExe)) {
        Write-Log "Python 3.11: Cài đặt thành công tại $pyExe" "SUCCESS"
    } else {
        Write-Log "Python 3.11: Cài đặt thất bại." "ERROR"
    }
}

# 3. PostgreSQL 16
$pgPostgresExe = Get-ToolPath "postgres"
if (Test-Path $pgPostgresExe) {
    Write-Log "PostgreSQL: Đã tồn tại tại $pgPostgresExe"
} else {
    Write-Log "PostgreSQL: Đang tải và giải nén binaries $PG_VERSION..."
    $pgZip = Join-Path $downloadsDir "postgresql-$PG_VERSION-windows-x64-binaries.zip"
    $pgUrl = "https://get.enterprisedb.com/postgresql/postgresql-$PG_VERSION-windows-x64-binaries.zip"
    if (Download-FileWithCurlOrWebClient $pgUrl $pgZip) {
        # Giải nén
        $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
        if ($tar) {
            & tar.exe -xf $pgZip -C $script:ToolsDir
        } else {
            Expand-Archive -Path $pgZip -DestinationPath $script:ToolsDir -Force
        }
        # Dọn dẹp thư mục không cần thiết
        Remove-Item -Recurse -Force (Join-Path $script:ToolsDir "pgsql\pgAdmin 4"), (Join-Path $script:ToolsDir "pgsql\StackBuilder"), (Join-Path $script:ToolsDir "pgsql\doc") -ErrorAction SilentlyContinue
        Remove-Item -Force $pgZip -ErrorAction SilentlyContinue
        Write-Log "PostgreSQL 16: Cài đặt thành công." "SUCCESS"
    } else {
        Write-Log "PostgreSQL: Tải thất bại. Vui lòng tải từ $pgUrl và đặt vào $pgZip" "ERROR"
    }
}

# 4. Mosquitto 2.0.x
$mosqExe = Get-ToolPath "mosquitto"
if (Test-Path $mosqExe) {
    Write-Log "Mosquitto: Đã tồn tại tại $mosqExe"
} else {
    Write-Log "Mosquitto: Đang tải bộ cài $MOSQ_VERSION..."
    $mosqInstaller = Join-Path $downloadsDir "mosquitto-$MOSQ_VERSION-install-windows-x64.exe"
    $mosqUrl = "https://mosquitto.org/files/binary/win64/mosquitto-$MOSQ_VERSION-install-windows-x64.exe"
    if (Download-FileWithCurlOrWebClient $mosqUrl $mosqInstaller) {
        $mosqDir = Join-Path $script:ToolsDir "mosquitto"
        Write-Log "Mosquitto: Cài đặt im lặng vào $mosqDir..."
        $proc = Start-Process -FilePath $mosqInstaller -ArgumentList '/S', "/D=$mosqDir" -Wait -PassThru
        Start-Sleep -Seconds 2
        
        # Nếu bộ cài đăng ký service mosquitto, dừng và xóa service đó
        if (Get-Service mosquitto -ErrorAction SilentlyContinue) {
            Write-Log "Mosquitto: Đã đăng ký Windows service, tiến hành dừng và gỡ service..." "WARN"
            Stop-Service mosquitto -ErrorAction SilentlyContinue
            & sc.exe delete mosquitto | Out-Null
        }
        Remove-Item -Force $mosqInstaller -ErrorAction SilentlyContinue
        Write-Log "Mosquitto 2.0.x: Cài đặt thành công." "SUCCESS"
    } else {
        Write-Log "Mosquitto: Tải thất bại. Vui lòng tải từ $mosqUrl và đặt vào $mosqInstaller" "ERROR"
    }
}

# 5. Node.js 20 LTS
$nodeExe = Get-ToolPath "node"
if (Test-Path $nodeExe) {
    Write-Log "Node.js: Đã tồn tại tại $nodeExe"
} else {
    Write-Log "Node.js: Đang tải phiên bản $NODE_VERSION..."
    $nodeZip = Join-Path $downloadsDir "node-$NODE_VERSION-win-x64.zip"
    $nodeUrl = "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-win-x64.zip"
    if (Download-FileWithCurlOrWebClient $nodeUrl $nodeZip) {
        $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
        if ($tar) {
            & tar.exe -xf $nodeZip -C $script:ToolsDir
        } else {
            Expand-Archive -Path $nodeZip -DestinationPath $script:ToolsDir -Force
        }
        $extractedNodeDir = Join-Path $script:ToolsDir "node-$NODE_VERSION-win-x64"
        $finalNodeDir = Join-Path $script:ToolsDir "node"
        if (Test-Path $extractedNodeDir) {
            Move-Item -Path $extractedNodeDir -Destination $finalNodeDir -Force
        }
        Remove-Item -Force $nodeZip -ErrorAction SilentlyContinue
        Write-Log "Node.js 20 LTS: Cài đặt thành công." "SUCCESS"
    } else {
        Write-Log "Node.js: Tải thất bại. Vui lòng tải từ $nodeUrl và đặt vào $nodeZip" "ERROR"
    }
}

# Dọn dẹp thư mục tạm _downloads nếu rỗng
if (Test-Path $downloadsDir) {
    if ((Get-ChildItem $downloadsDir | Measure-Object).Count -eq 0) {
        Remove-Item -Force $downloadsDir -ErrorAction SilentlyContinue
    }
}

# Ghi tools/VERSIONS.txt
$versionsTxt = Join-Path $script:ToolsDir "VERSIONS.txt"
$versionsContent = @"
uv=$UV_VERSION
python=3.11.11
postgresql=16.4
mosquitto=$MOSQ_VERSION
nodejs=20.18.0
"@
[System.IO.File]::WriteAllText($versionsTxt, $versionsContent, [System.Text.Encoding]::UTF8)

Write-Log "=== Hoàn tất get-tools.ps1 ===" "SUCCESS"

