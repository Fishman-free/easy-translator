# Easy Translator 桌面伴生 —— 一键启动
# 用法：右键「使用 PowerShell 运行」，或  powershell -ExecutionPolicy Bypass -File run.ps1
#        run.ps1 --selftest   只跑自检
#        run.ps1 --settings   只开设置窗口，不监听
# 参数原样透传给 python -m et_desktop（新增参数不用再改这个脚本）
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "首次运行：创建虚拟环境并安装依赖…" -ForegroundColor Cyan
    python -m venv .venv
    & $py -m pip install --quiet --upgrade pip
    & $py -m pip install --quiet -r requirements.txt
}

& $py -m et_desktop @args
