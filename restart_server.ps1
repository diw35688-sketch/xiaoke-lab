
# 一键重启 D:\me\ai107 的 FastAPI/Uvicorn 服务
# 用法: powershell -File D:\me\ai107\restart_server.ps1

$ErrorActionPreference = 'Stop'
$Port = 8000
$WorkDir = 'D:\me\ai107\web'
$Python = 'D:\me\ai107\.venv\Scripts\python.exe'
$Out = 'D:\me\ai107\uvicorn_out.log'
$Err = 'D:\me\ai107\uvicorn_err.log'

Write-Host "==> 停止旧服务 (port $Port)"
$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    $listeners | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
        Write-Host "  kill PID $_"
        Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host "  没有旧监听进程"
}
Start-Sleep -Seconds 2

Write-Host "==> 启动新服务"
Remove-Item -LiteralPath $Out,$Err -Force -ErrorAction SilentlyContinue
$p = Start-Process -FilePath $Python `
    -ArgumentList '-m','uvicorn','app:app','--app-dir',$WorkDir,'--host','0.0.0.0','--port',$Port `
    -WorkingDirectory $WorkDir `
    -RedirectStandardOutput $Out -RedirectStandardError $Err `
    -PassThru -WindowStyle Hidden
Write-Host "  started PID $($p.Id)"

Write-Host "==> 等待健康检查"
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Write-Host "  OK: http://127.0.0.1:$Port/health"
            exit 0
        }
    } catch {}
}
Write-Host "  启动超时，请查看 $Err" -ForegroundColor Red
exit 1
