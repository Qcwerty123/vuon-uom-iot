# cam-sim.ps1 — Camera giả Node 2 (tests/load/cam_sim.py) cho WP-07, dùng môi trường Python của backend
# Ví dụ:
#   .\scripts\windows\cam-sim.ps1 register                      # đăng ký + cấp phát camera giả qua API
#   .\scripts\windows\cam-sim.ps1 run --image sick               # chạy: nhận lệnh "Chụp ngay" trên web → upload → ack
#   .\scripts\windows\cam-sim.ps1 run --image healthy --interval-min 1   # chụp theo chu kỳ 1 phút
#   .\scripts\windows\cam-sim.ps1 upload --image sick            # upload một ảnh rồi thoát
# Tương thích Windows PowerShell 5.1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")
$py = Ensure-Venv (Get-RepoPath "backend/api")
if (-not $py) { exit 1 }
$env:PYTHONIOENCODING = "utf-8"
& $py (Get-RepoPath "tests/load/cam_sim.py") @args
exit $LASTEXITCODE
