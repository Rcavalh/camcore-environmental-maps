#!/usr/bin/env bash
set -euo pipefail

runtime_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
inferred_project_root="$(cd "$runtime_dir/../../../.." && pwd)"
export FROST_PROJECT_ROOT="${FROST_PROJECT_ROOT:-$inferred_project_root}"
export FROST_MODULE="$FROST_PROJECT_ROOT/8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration"
export FROST_PYTHON_BIN="${FROST_PYTHON_BIN:-python}"
export FROST_HPC_INPUT="${FROST_HPC_INPUT:-$FROST_MODULE/hpc_full_native_rf/data}"
export FROST_CONFIG="$FROST_MODULE/hpc_full_native_rf/config/source_roots_hpc.json"
export FROST_MODEL="$FROST_MODULE/outputs/balanced_models_10000_temporal_enso/models/RF_BLOCK_BALANCED_ALL_ENDPOINTS.joblib"
export FROST_ENSO="$FROST_PROJECT_ROOT/4.Modelling/articles/tables/temporal_enso/NOAA_RONI_FROST_SEASON_2000_2025.csv"
export FROST_OUTPUT="${FROST_OUTPUT:-$FROST_MODULE/outputs/hpc_full_native_balanced_rf}"

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export GDAL_CACHEMAX="${GDAL_CACHEMAX:-4096}"

mkdir -p "$FROST_MODULE/hpc_full_native_rf/logs" "$FROST_OUTPUT"
cd "$FROST_PROJECT_ROOT"
