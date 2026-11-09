# sim.ps1 — Chạy thiết bị mô phỏng (tests/load/simulator.py) bằng Python trong tools/
# Lần đầu tự tạo môi trường tests/load/.venv và cài paho-mqtt.
# Ví dụ:
#   .\scripts\windows\sim.ps1 provision --count 1          # tạo tài khoản broker ctl-9001
#   .\scripts\windows\sim.ps1 run                           # chạy thiết bị mô phỏng
#   .\scripts\windows\sim.ps1 watch                         # (cửa sổ khác) xem bản tin như backend
#   .\scripts\windows\sim.ps1 cmd ctl-9001 pump_on --duration 5
#   .\scripts\windows\sim.ps1 config ctl-9001 --set soil_low=40 --set soil_high=60
# Tương thích Windows PowerShell 5.1

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "common.ps1")

$venv = Get-RepoPath "tests/load/.venv"
$py = Join-Path $venv "Scripts\python.exe"
$uv = Get-ToolPath "uv"
$env:UV_CACHE_DIR = Get-RepoPath "tools/uv/.cache"
$env:UV_PYTHON_INSTALL_DIR = Get-RepoPath "tools/python"

if (-not (Test-Path $py)) {
    Write-Log "Tạo môi trường Python cho thiết bị mô phỏng..."
    & $uv venv $venv --python (Get-ToolPath "python") | Out-Host
    & $uv pip install --python $py -r (Get-RepoPath "tests/load/requirements.txt") | Out-Host
    if (-not (Test-Path $py)) { Write-Log "Tạo môi trường thất bại" "ERROR"; exit 1 }
}

$env:PYTHONIOENCODING = "utf-8"
& $py (Get-RepoPath "tests/load/simulator.py") @args
exit $LASTEXITCODE
