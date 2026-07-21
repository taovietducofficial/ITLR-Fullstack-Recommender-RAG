# Cap nhat RECOMMENDER_URL trong web/.env theo IP WSL hien tai (IP doi sau moi reboot).
# Chay SAU khi Docker Desktop da len: powershell -File scripts\fix_recommender_ip.ps1
# Ly do: proxy port-forward 127.0.0.1:8000 cua Docker Desktop bi nghen (~4KB/s),
# di thang IP VM WSL nhanh gap ~30 lan. Xem ghi chu trong web/.env.

$envFile = Join-Path $PSScriptRoot "..\web\.env"

$ip = (wsl -d docker-desktop sh -c "ip -4 addr show eth0" | Select-String "inet (\d+\.\d+\.\d+\.\d+)").Matches.Groups[1].Value
if (-not $ip) { Write-Host "[LOI] Khong lay duoc IP WSL - Docker Desktop da chay chua?" -ForegroundColor Red; exit 1 }

$content = Get-Content $envFile -Raw
$new = $content -replace "(?m)^RECOMMENDER_URL=http://\d+\.\d+\.\d+\.\d+:8000", "RECOMMENDER_URL=http://${ip}:8000"
if ($new -eq $content) { Write-Host "[OK] web/.env da dung IP $ip - khong can sua." -ForegroundColor Green }
else {
    Set-Content $envFile $new -Encoding utf8 -NoNewline
    Write-Host "[OK] Da cap nhat RECOMMENDER_URL -> http://${ip}:8000" -ForegroundColor Green
    # Cham server.ts de tsx watch tu nap lai .env (neu web dang chay)
    $serverTs = Join-Path $PSScriptRoot "..\web\src\server.ts"
    (Get-Item $serverTs).LastWriteTime = Get-Date
}

# Kiem tra nhanh recommender co tra loi qua IP moi khong
try {
    $r = Invoke-WebRequest "http://${ip}:8000/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "[OK] Recommender tra loi qua ${ip}:8000 - san sang." -ForegroundColor Green
} catch {
    Write-Host "[!] Recommender chua tra loi (container co the dang nap model ~2 phut). Thu lai sau." -ForegroundColor Yellow
}
