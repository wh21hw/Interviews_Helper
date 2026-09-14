$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectDir '.venv\Scripts\python.exe'

$internetSettings = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
if ($internetSettings.ProxyEnable -eq 1 -and $internetSettings.ProxyServer) {
    $proxyValue = [string]$internetSettings.ProxyServer
    if ($proxyValue -notmatch '^https?://') {
        $proxyValue = "http://$proxyValue"
    }
    $env:HTTP_PROXY = $proxyValue
    $env:HTTPS_PROXY = $proxyValue
    $env:NO_PROXY = 'localhost,127.0.0.1'
    $env:no_proxy = 'localhost,127.0.0.1'
    Write-Host "本次进程使用 Windows 代理：$proxyValue"
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $projectDir '.venv')
}

& $pythonPath -c 'import playwright, rapidocr, onnxruntime, interviews_helper' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '正在安装 Playwright Python 包……'
    & $pythonPath -m pip install --no-build-isolation -e $projectDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host '当前 pip 不支持 editable build，尝试 setuptools develop 兼容模式……'
        & $pythonPath (Join-Path $projectDir 'setup.py') develop
        if ($LASTEXITCODE -ne 0) {
            throw '项目依赖安装失败。请检查代理或网络后重试。'
        }
    }
}

& $pythonPath -m interviews_helper @args
exit $LASTEXITCODE
