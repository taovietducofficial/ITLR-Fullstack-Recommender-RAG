# Wrapper cho Windows Task Scheduler: chạy pipeline cập nhật dữ liệu bằng Python trong .venv,
# ghi log có dấu thời gian vào reports\. Tham số truyền thẳng cho update_data.py (vd --max 300).
#
# CHẠY TAY:
#   powershell -ExecutionPolicy Bypass -File scripts\update_data.ps1 --max 300 --no-translate
#
# ĐĂNG KÝ CHẠY ĐỊNH KỲ (vd Chủ nhật 2h sáng) — chạy 1 lần trong PowerShell tại thư mục gốc repo:
#   $repo = (Get-Location).Path
#   $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
#       -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\scripts\update_data.ps1`" --max 300 --no-translate"
#   $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 2am
#   Register-ScheduledTask -TaskName "ITLR-UpdateData" -Action $action -Trigger $trigger `
#       -Description "Cào + gộp + UPSERT Postgres + rebuild model"
# Gỡ lịch:  Unregister-ScheduledTask -TaskName "ITLR-UpdateData" -Confirm:$false
#
# YÊU CẦU môi trường khi chạy: Postgres đang chạy (web/.env DATABASE_URL đúng) + npm trên PATH +
# internet để cào. Recommender (:8000) KHÔNG cần chạy; build_model ghi artifacts trực tiếp.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot      # scripts\ -> thư mục gốc repo
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }   # fallback nếu không có venv

$logDir = Join-Path $Root "reports"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("update_data_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Write-Output "[$(Get-Date -Format s)] Bắt đầu pipeline -> log: $log"
& $py "scripts\update_data.py" @args *>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
Write-Output "[$(Get-Date -Format s)] Kết thúc, exit=$code"
exit $code
