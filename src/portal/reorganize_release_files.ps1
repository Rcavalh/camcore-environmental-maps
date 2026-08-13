param(
    [string]$PortalRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
)

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath($PortalRoot)
if ([System.IO.Path]::GetFileName($root) -ne "8.2_CODEX_portal_maps") {
    throw "Refusing to reorganize unexpected directory: $root"
}

$modelRoot = Join-Path $root "dryad_dataset\data\model_outputs"
$archive = Join-Path $root "backup\replaced_complete_period_2026-08-10"
New-Item -ItemType Directory -Force -Path $modelRoot, $archive | Out-Null

$records = [System.Collections.Generic.List[object]]::new()
function Move-TrackedFile([string]$relativeSource, [string]$relativeDestination, [bool]$copyIfLocked = $false) {
    $source = Join-Path $root $relativeSource
    $destination = Join-Path $root $relativeDestination
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        $status = if (Test-Path -LiteralPath $destination -PathType Leaf) { "ALREADY_ORGANIZED" } else { "SOURCE_MISSING" }
        $records.Add([pscustomobject]@{OldPath=$relativeSource; NewPath=$relativeDestination; Status=$status})
        return
    }
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if (Test-Path -LiteralPath $destination) {
        if ((Get-Item -LiteralPath $source).Length -eq (Get-Item -LiteralPath $destination).Length) {
            $records.Add([pscustomobject]@{OldPath=$relativeSource; NewPath=$relativeDestination; Status="ALREADY_ORGANIZED"})
            return
        }
        throw "Destination already exists with a different size: $destination"
    }
    try {
        Move-Item -LiteralPath $source -Destination $destination
        $records.Add([pscustomobject]@{OldPath=$relativeSource; NewPath=$relativeDestination; Status="MOVED"})
    } catch [System.IO.IOException] {
        if (-not $copyIfLocked) { throw }
        Copy-Item -LiteralPath $source -Destination $destination
        $records.Add([pscustomobject]@{OldPath=$relativeSource; NewPath=$relativeDestination; Status="COPIED_SOURCE_LOCKED"})
    }
}

$moves = @(
    @("dryad_dataset\data\model_outputs\complete_period\RF_REDUCED_BLOCK_BALANCED_SEASONAL_MINIMUM_TEMPERATURE_C_2000_2025_ANADEM30M_PR_SC_RS_SP_MS.tif", "dryad_dataset\data\model_outputs\complete_period\TMIN_MEAN_2000_2025.tif", $true),
    @("RF_BALANCED_FROST_PROBABILITY_ALL_2000_2025_ANADEM30M.tif", "dryad_dataset\data\model_outputs\complete_period\FROST_PROBABILITY_MEAN_2000_2025.tif"),
    @("RF_BALANCED_EXPECTED_FROST_DAYS_ALL_2000_2025_ANADEM30M.tif", "dryad_dataset\data\model_outputs\complete_period\FROST_DAYS_MEAN_2000_2025.tif"),
    @("RF_BALANCED_SEASONAL_MINIMUM_TEMPERATURE_C_P25_ALL_2000_2025_ANADEM30M.tif", "dryad_dataset\data\model_outputs\complete_period\TMIN_P25_2000_2025.tif"),


    @("backup\RF_BALANCED_FROST_PROBABILITY_ENSO_EL_NINO_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\el_nino\frost_probability_enso_el_nino.tif"),
    @("RF_BALANCED_EXPECTED_FROST_DAYS_ENSO_EL_NINO_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\el_nino\expected_frost_days_enso_el_nino.tif"),
    @("RF_BALANCED_SEASONAL_MINIMUM_TEMPERATURE_C_P25_ENSO_EL_NINO_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\el_nino\seasonal_minimum_temperature_p25_enso_el_nino.tif"),
    @("backup\RF_BALANCED_FROST_PROBABILITY_ENSO_LA_NINA_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\la_nina\frost_probability_enso_la_nina.tif"),
    @("RF_BALANCED_EXPECTED_FROST_DAYS_ENSO_LA_NINA_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\la_nina\expected_frost_days_enso_la_nina.tif"),
    @("RF_BALANCED_SEASONAL_MINIMUM_TEMPERATURE_C_P25_ENSO_LA_NINA_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\la_nina\seasonal_minimum_temperature_p25_enso_la_nina.tif"),
    @("backup\RF_BALANCED_FROST_PROBABILITY_ENSO_NEUTRAL_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\neutral\frost_probability_enso_neutral.tif"),
    @("RF_BALANCED_EXPECTED_FROST_DAYS_ENSO_NEUTRAL_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\neutral\expected_frost_days_enso_neutral.tif"),
    @("RF_BALANCED_SEASONAL_MINIMUM_TEMPERATURE_C_P25_ENSO_NEUTRAL_ANADEM30M.tif", "dryad_dataset\data\model_outputs\enso\neutral\seasonal_minimum_temperature_p25_enso_neutral.tif")
)

foreach ($move in $moves) {
    $copyIfLocked = if ($move.Count -gt 2) { [bool]$move[2] } else { $false }
    Move-TrackedFile $move[0] $move[1] $copyIfLocked
}

# These two earlier complete-period copies are redundant. Archive them when
# ArcGIS or another desktop application is not holding an open file handle.
$redundant = @(
    "RF_REDUCED_BLOCK_BALANCED_FROST_OCCURRENCE_PROBABILITY_2000_2025_ANADEM30M_PR_SC_RS_SP_MS.tif",
    "RF_REDUCED_BLOCK_BALANCED_EXPECTED_FROST_DAYS_PER_SEASON_2000_2025_ANADEM30M_PR_SC_RS_SP_MS.tif"
)
foreach ($name in $redundant) {
    $source = Join-Path $modelRoot "complete_period\$name"
    $destination = Join-Path $archive $name
    if (-not (Test-Path -LiteralPath $source)) { continue }
    if (Test-Path -LiteralPath $destination) { continue }
    try {
        Move-Item -LiteralPath $source -Destination $destination
        $records.Add([pscustomobject]@{OldPath="dryad_dataset\data\model_outputs\complete_period\$name"; NewPath="backup\replaced_complete_period_2026-08-10\$name"; Status="ARCHIVED"})
    } catch [System.IO.IOException] {
        $records.Add([pscustomobject]@{OldPath="dryad_dataset\data\model_outputs\complete_period\$name"; NewPath="backup\replaced_complete_period_2026-08-10\$name"; Status="CLEANUP_PENDING_FILE_LOCKED"})
    }
}

$manifest = Join-Path $root "dryad_dataset\metadata\FILE_ORGANIZATION_2026-08-10.csv"
$records | Export-Csv -LiteralPath $manifest -NoTypeInformation -Encoding UTF8
Write-Output "RELEASE_FILES_ORGANIZED=$($records.Where({$_.Status -in @('MOVED','COPIED_SOURCE_LOCKED','ARCHIVED')}).Count)"
Write-Output "ORGANIZATION_MANIFEST=$manifest"
