#!/usr/bin/env bash
set -euo pipefail
project_dir="${1:-$PWD}"
cd "$project_dir"
base="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf"
mkdir -p "$base/logs"
bsub < "$base/hpc/01_finalize_rf_reduced_10000_cnr.sh"
