# 关闭桌面伴生（与 run.ps1 对称）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File desktop\stop.ps1
# 也可以直接在界面里点「退出桌面取词」按钮（设置窗口底部）。
$procs = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like '*et_desktop*' }
if (-not $procs) {
    Write-Host "桌面伴生未在运行"
    exit 0
}
foreach ($p in $procs) {
    Write-Host "结束 PID $($p.ProcessId)…"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 500
$left = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like '*et_desktop*' }
if ($left) { Write-Host "仍有残留进程，请重跑一次或到任务管理器结束 python" ; exit 1 }
Write-Host "桌面伴生已关闭 ✓"
