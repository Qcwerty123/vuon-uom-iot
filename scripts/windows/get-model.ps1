# get-model.ps1 — Tải trọng số mô hình AI về runtime/ai/models/ và kiểm SHA256 (đặc tả §15.5, C24)
# Thông tin mô hình (link, SHA256, giấy phép) nằm trong backend/ai-service/model.json.
#   .\scripts\windows\get-model.ps1          # tải nếu chưa có hoặc SHA256 sai
#   .\scripts\windows\get-model.ps1 -Force   # tải lại
# Tương thích Windows PowerShell 5.1

[CmdletBinding()]
param([switch]$Force)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
Import-EnvFile | Out-Null

$manifest = Get-Content -Raw -Encoding UTF8 (Get-RepoPath "backend/ai-service/model.json") | ConvertFrom-Json
$modelDirRel = if ($env:AI_MODEL_DIR) { $env:AI_MODEL_DIR } else { "runtime/ai/models" }
$modelDir = Get-RepoPath $modelDirRel
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
$target = Join-Path $modelDir $manifest.file
$want = $manifest.sha256.ToUpper()

Write-Log "=== Mô hình: $($manifest.model_version) — $($manifest.name) ==="
Write-Log "Nguồn: $($manifest.source) · Giấy phép: $($manifest.license)"

if ((Test-Path $target) -and -not $Force) {
    $have = (Get-FileHash $target -Algorithm SHA256).Hash
    if ($have -eq $want) {
        Write-Log "Đã có trọng số đúng SHA256: $target" "SUCCESS"
        exit 0
    }
    Write-Log "SHA256 của file hiện có không khớp, tải lại." "WARN"
}

$part = "$target.part"
Remove-Item -Force $part -ErrorAction SilentlyContinue
Write-Log "Đang tải $($manifest.url) ($([math]::Round($manifest.size_bytes / 1MB, 1)) MB)..."
$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
$ok = $false
if ($curl) {
    & curl.exe -f -sSL --retry 3 $manifest.url -o $part
    $ok = ($LASTEXITCODE -eq 0 -and (Test-Path $part))
}
if (-not $ok) {
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        (New-Object System.Net.WebClient).DownloadFile($manifest.url, $part)
        $ok = Test-Path $part
    } catch {
        Write-Log "Tải thất bại: $_" "ERROR"
    }
}
if (-not $ok) { exit 1 }

$have = (Get-FileHash $part -Algorithm SHA256).Hash
if ($have -ne $want) {
    Write-Log "SHA256 không khớp: tải được $have, cần $want. Đã xóa file tải." "ERROR"
    Remove-Item -Force $part -ErrorAction SilentlyContinue
    exit 1
}
Move-Item -Force $part $target
Write-Log "Đã lưu $target (SHA256 khớp). Khởi động lại AI service: stop.ps1 -OnlyAi; start.ps1" "SUCCESS"
