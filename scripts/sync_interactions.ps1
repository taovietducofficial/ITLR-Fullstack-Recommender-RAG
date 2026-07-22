# Wrapper cho Windows Task Scheduler: đồng bộ interactions_real.csv từ DataLake lakehouse
# (Trino) rồi rebuild CF model, ghi log có dấu thời gian vào reports\.
# Tham số truyền thẳng cho sync_interactions_from_datalake.py (vd --min-users 20).
#
# CHẠY TAY:
#   powershell -ExecutionPolicy Bypass -File scripts\sync_interactions.ps1 --rebuild-cf
#
# ĐĂNG KÝ CHẠY ĐỊNH KỲ (3h30 sáng, sau schedule Dagster lúc 3h00) — chạy 1 lần trong PowerShell
# tại thư mục gốc repo:
#   $repo = (Get-Location).Path
#   $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
#       -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$repo\scripts\sync_interactions.ps1`" --rebuild-cf"
#   $trigger = New-ScheduledTaskTrigger -Daily -At 3:30am
#   Register-ScheduledTask -TaskName "ITLR-SyncInteractions" -Action $action -Trigger $trigger `
#       -Description "Đồng bộ tương tác thật từ DataLake lakehouse (Trino) + rebuild CF"
# Gỡ lịch:  Unregister-ScheduledTask -TaskName "ITLR-SyncInteractions" -Confirm:$false
#
# YÊU CẦU môi trường khi chạy: DataLake/ đang chạy (docker compose up, Trino nghe :8082) và job
# Dagster `sync_itlr_interactions` đã materialize gold.itlr_fact_interaction.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot      # scripts\ -> thư mục gốc repo
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }   # fallback nếu không có venv

$logDir = Join-Path $Root "reports"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir ("sync_interactions_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Write-Output "[$(Get-Date -Format s)] Bắt đầu đồng bộ tương tác thật -> log: $log"
& $py "scripts\data\sync_interactions_from_datalake.py" @args *>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
Write-Output "[$(Get-Date -Format s)] Kết thúc, exit=$code"
exit $code
