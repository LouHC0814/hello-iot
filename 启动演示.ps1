param(
    [switch]$实时,
    [int]$样本数 = 120,
    [double]$回放间隔 = 0.3,
    [string]$解释器 = (Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)) "AppData/Local/Programs/Python/Python313/python.exe")
)

$ErrorActionPreference = "Stop"
$demoPython = $解释器
if (-not (Test-Path -LiteralPath $demoPython)) {
    throw "未找到 Python 3.13。请按照 README，用你安装的 Python 解释器绝对路径运行。"
}
$demoPython = (Resolve-Path -LiteralPath $demoPython).ProviderPath

$runtimeRoot = Join-Path $PSScriptRoot ".runtime"
$configNames = @{
    IPYTHONDIR = "ipython"
    JUPYTER_CONFIG_DIR = "jupyter/config"
    JUPYTER_DATA_DIR = "jupyter/data"
    JUPYTER_RUNTIME_DIR = "jupyter/runtime"
    MPLCONFIGDIR = "matplotlib"
}
foreach ($configName in $configNames.Keys) {
    $configPath = Join-Path $runtimeRoot $configNames[$configName]
    New-Item -ItemType Directory -Path $configPath -Force | Out-Null
    [Environment]::SetEnvironmentVariable($configName, $configPath, "Process")
}
$env:PYTHONIOENCODING = "utf-8"
$demoArguments = @("-m", "iot_demo", "--samples", [string]$样本数, "--refresh", $回放间隔.ToString([Globalization.CultureInfo]::InvariantCulture))
if ($实时) { $demoArguments += "--live" }

Push-Location -LiteralPath $PSScriptRoot
try {
    & $demoPython @demoArguments
    if ($LASTEXITCODE -ne 0) { throw "演示运行失败，退出码：$LASTEXITCODE" }
} finally {
    Pop-Location
}
