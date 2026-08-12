$ErrorActionPreference = "Stop"
$module = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$modisMarker = Join-Path $module "database/HISTORICAL_MODIS_STATION_YEAR_OK.json"
$resultMarker = Join-Path $module "outputs/historical_paired_model_statistics/HISTORICAL_PAIRED_RF_STATISTICS_OK"
$activeMarker = Join-Path $module "checkpoints/HISTORICAL_STATISTICS_ORCHESTRATOR_ACTIVE"
$python = if ($env:FROST_PYTHON_BIN) { $env:FROST_PYTHON_BIN } else { "python" }
$script = Join-Path $module "scripts/11_validate_historical_paired_models.py"
$logDir = Join-Path $module "logs"
$stdout = Join-Path $logDir "historical_paired_statistics.out"
$stderr = Join-Path $logDir "historical_paired_statistics.err"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if (Test-Path $resultMarker) { exit 0 }
Set-Content -LiteralPath $activeMarker -Value "pid=$PID`nstarted_at=$([DateTimeOffset]::Now.ToString('o'))"
try {
    while (-not (Test-Path $modisMarker)) { Start-Sleep -Seconds 15 }
    & $python $script 1> $stdout 2> $stderr
    if ($LASTEXITCODE -ne 0) { throw "Historical paired statistics failed with exit code $LASTEXITCODE" }
}
finally {
    if (Test-Path $activeMarker) { Remove-Item -LiteralPath $activeMarker -Force }
}
