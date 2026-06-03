# 清理 MetaForge 占用的所有后端端口，便于在 8008 只启一个实例
$ErrorActionPreference = "Continue"
$root = Split-Path $PSScriptRoot -Parent
$officialPort = 8008
$ports = @(8000, 8008, 8010)

Write-Host "[1/3] 结束 main.py / uvicorn 相关 Python 进程 ..."
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'tests\\main\.py|main:app|uvicorn\.run\(''main:app''' } |
    ForEach-Object {
        Write-Host "  taskkill /T /PID $($_.ProcessId)"
        taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null
    }

Write-Host "[2/3] 按端口结束仍存活的监听进程（最多 5 轮）..."
foreach ($round in 1..5) {
    $pids = @()
    foreach ($port in $ports) {
        $pids += netstat -ano | Select-String ":$port\s+.*LISTENING" | ForEach-Object { ($_ -split '\s+')[-1] }
    }
    $pids = $pids | Where-Object { $_ -and $_ -ne '0' } | Sort-Object -Unique
    if (-not $pids.Count) { break }
    foreach ($p in $pids) {
        if (Get-Process -Id $p -ErrorAction SilentlyContinue) {
            taskkill /F /T /PID $p 2>$null | Out-Null
        }
    }
    Start-Sleep -Seconds 1
}

Write-Host "[3/3] Port check (official=$officialPort) ..."
python -c "import socket
for port in (8000,8008,8010):
 s=socket.socket()
 try:
  s.bind(('127.0.0.1',port));s.close();print(port,'free')
 except OSError:
  print(port,'busy')"

$bindOk = python -c "import socket,sys;s=socket.socket();
exec('try:\n s.bind((\"127.0.0.1\",8008));s.close()\nexcept OSError:\n sys.exit(1)')" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARN: port 8008 still busy. Reboot Windows if taskkill failed."
}
Write-Host "Next: .\scripts\restart_backend.ps1"
