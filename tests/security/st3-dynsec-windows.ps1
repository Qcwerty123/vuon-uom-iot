# st3-dynsec-windows.ps1 — Kiểm chứng C18 / ST3 / ST4 trên Windows
#   1. Khóa thiết bị (disableClient) có ngắt ngay phiên đang mở không
#   2. Kết nối lại bằng secret cũ bị từ chối; mở khóa thì kết nối lại được
#   3. Thiết bị không publish được sang nhánh thiết bị khác (ST4)
#   4. Thay đổi dynsec còn sau khi khởi động lại broker (lỗi lưu file trên Windows)
# Kết quả: logs/tests/st3-dynsec-windows.txt · Tương thích Windows PowerShell 5.1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$winDir = Join-Path $scriptDir "..\..\scripts\windows"
. (Join-Path $winDir "common.ps1")
Import-EnvFile | Out-Null

$out = Get-RepoPath "logs/tests/st3-dynsec-windows.txt"
$script:CurrentLogFile = $out
"# ST3/ST4/C18 — $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Set-Content -Encoding UTF8 $out
$dev = Join-Path $winDir "dev-device.ps1"
$code = "test-0001"
$secretFile = Get-RepoPath "runtime/pids/st3-secret.tmp"
$results = [ordered]@{}

& $dev delete -Code $code *> $null   # dọn dẹp lần chạy trước (nếu có)
& $dev create -Code $code -SecretOutFile $secretFile *> $null
if (-not (Test-Path $secretFile)) { Write-Log "Không tạo được thiết bị thử $code" "ERROR"; exit 1 }
$secret = (Get-Content $secretFile -Raw).Trim()
Remove-Item -Force $secretFile

# --- ST4 + quyền cơ bản ---
$results["Thiet bi publish nhanh cua minh"] = Test-MqttPublish $code $secret "nursery/g01/$code/telemetry" "st3-own"
$results["ST4: publish sang nhanh cam-0001 (phai DENIED)"] = Test-MqttPublish $code $secret "nursery/g01/cam-0001/telemetry" "st3-other"

# --- ST3: phiên đang mở bị ngắt khi khóa ---
$subLog = Get-RepoPath "logs/tests/st3-sub-output.txt"
$subErr = Get-RepoPath "logs/tests/st3-sub-error.txt"
$subArgs = "-h 127.0.0.1 -p 1883 -V mqttv5 -i st3-sub -u $code -P $secret -t nursery/g01/$code/command -v"
$sub = Start-Process -FilePath (Get-ToolPath "mosquitto_sub") -ArgumentList $subArgs -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $subLog -RedirectStandardError $subErr
Start-Sleep -Seconds 2
$results["Phien mo truoc khi khoa"] = if (-not $sub.HasExited) { "OK" } else { "ERROR" }

& $dev disable -Code $code *> $null
Start-Sleep -Seconds 3
$mqLog = Get-Content (Get-RepoPath "logs/services/mosquitto.log") -Tail 40 | Where-Object { $_ -match "st3-sub" }
$kicked = $sub.HasExited -or ($mqLog -match "(?i)disconnect|closed|not authori")
$results["ST3: khoa thi phien dang mo bi ngat"] = if ($kicked) { "OK" } else { "KHONG NGAT" }
if (-not $sub.HasExited) { Stop-Process -Id $sub.Id -Force -ErrorAction SilentlyContinue }

$results["ST3: ket noi lai bang secret cu khi dang khoa (phai AUTH_FAILED)"] = Test-MqttPublish $code $secret "nursery/g01/$code/telemetry" "st3-again"
& $dev enable -Code $code *> $null
$results["Mo khoa roi ket noi lai"] = Test-MqttPublish $code $secret "nursery/g01/$code/telemetry" "st3-back"

# --- Lưu dynsec qua khởi động lại broker ---
& (Join-Path $winDir "stop.ps1") -OnlyBroker *> $null
& (Join-Path $winDir "start.ps1") *> $null
$results["Dynsec con sau khi khoi dong lai broker"] = Test-MqttPublish $code $secret "nursery/g01/$code/telemetry" "st3-persist"

& $dev delete -Code $code *> $null
$results["Xoa thiet bi thi khong dang nhap duoc"] = Test-MqttPublish $code $secret "nursery/g01/$code/telemetry" "st3-deleted"

$expect = @{ "ST4: publish sang nhanh cam-0001 (phai DENIED)" = "DENIED";
             "ST3: ket noi lai bang secret cu khi dang khoa (phai AUTH_FAILED)" = "AUTH_FAILED";
             "Xoa thiet bi thi khong dang nhap duoc" = "AUTH_FAILED" }
$fail = 0
foreach ($k in $results.Keys) {
    $want = if ($expect.ContainsKey($k)) { $expect[$k] } else { "OK" }
    $pass = ($results[$k] -eq $want)
    if (-not $pass) { $fail++ }
    Write-Log ("{0,-4} {1} => {2} (mong doi {3})" -f $(if ($pass) { "PASS" } else { "FAIL" }), $k, $results[$k], $want) $(if ($pass) { "SUCCESS" } else { "ERROR" })
}
Write-Log "Dong log broker lien quan st3-sub:" "INFO"
$mqLog | ForEach-Object { Write-Log "  $_" "INFO" }
if ($fail -eq 0) { Write-Log "ST3/ST4/C18: DAT" "SUCCESS" } else { Write-Log "ST3/ST4/C18: $fail muc KHONG DAT" "ERROR" }
exit $fail
