#!/usr/bin/env bash
set -euo pipefail
runtime_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
inferred_project_root="$(cd "$runtime_dir/../../../.." && pwd)"
export FROST_PROJECT_ROOT="${FROST_PROJECT_ROOT:-$inferred_project_root}"
export FROST_MODULE="$FROST_PROJECT_ROOT/8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration"
export FROST_RUNROOT="$FROST_MODULE/hpc_article_v2_2_direct_grids_hand15_2000_2026"
export FROST_PYTHON_BIN="${FROST_PYTHON_BIN:-python}"
export FROST_HPC_INPUT="${FROST_HPC_INPUT:-$FROST_MODULE/hpc_full_native_rf/data}"
export FROST_CONFIG="$FROST_RUNROOT/config/source_roots_hpc.json"
export FROST_MODEL="$FROST_MODULE/outputs/hand15_rf_tabpfn_2000_2026/models/RF_HAND15_ALL_ENDPOINTS_2000_2026.joblib"
export FROST_DIRECT_INPUT="${FROST_DIRECT_INPUT:-$FROST_MODULE/hpc_article_v2_0_direct_grids_five_states/inputs/climate_annual}"
export FROST_ENSO_CSV="${FROST_ENSO_CSV:-$FROST_RUNROOT/config/NOAA_RONI_FROST_SEASON_2000_2026_FROZEN.csv}"
export FROST_OUTPUT="${FROST_OUTPUT:-$FROST_MODULE/outputs/article_v2_2_direct_grids_hand15/five_states_all_2000_2026}"
export FROST_EXPECTED_RASTERS=10
export FROST_MERGE_MARKER=ARTICLE_V2_2_HAND15_DIRECT_GRIDS_10MAPS_MERGE_OK
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export GDAL_CACHEMAX="${GDAL_CACHEMAX:-2048}"
mkdir -p "$FROST_RUNROOT/logs" "$FROST_OUTPUT"
cd "$FROST_PROJECT_ROOT"
