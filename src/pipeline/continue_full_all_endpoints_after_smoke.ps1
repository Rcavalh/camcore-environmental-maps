$ErrorActionPreference = 'Stop'
$module = '8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration'
$python = 'C:/Users/rcavalh/Documents/.virtualenvs/r-tabpfn/Scripts/python.exe'
$status = Join-Path $module 'outputs/full_native_five_state_rf_balanced_all_endpoints_period_enso/RUN_STATUS.json'

while (Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*29_predict_full_native_balanced_rf.py*--max-tiles*'
}) {
    Start-Sleep -Seconds 30
}

if (-not (Test-Path $status)) {
    'Smoke did not create RUN_STATUS.json; full run was not started.' | Set-Content (Join-Path $module 'logs/full_all_endpoints_launcher.err')
    exit 1
}

$active = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*29_predict_full_native_balanced_rf.py*' -and $_.CommandLine -notlike '*--max-tiles*'
}
if (-not $active) {
    & $python "$module/scripts/29_predict_full_native_balanced_rf.py" --tile-size 512 `
        1> "$module/logs/full_native_balanced_all_endpoints_period_enso.out" `
        2> "$module/logs/full_native_balanced_all_endpoints_period_enso.err"
}
