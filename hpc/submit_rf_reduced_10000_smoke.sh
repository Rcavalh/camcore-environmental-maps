#!/usr/bin/env bash
set -euo pipefail
project_dir="${1:-$PWD}"
cd "$project_dir"
base="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf"
mkdir -p "$base/logs"
job_id=$(bsub < "$base/hpc/01_rf_reduced_10000_smoke_cnr.sh" | sed -n 's/.*Job <\([0-9]*\)>.*/\1/p')
receipt="$base/logs/rf_reduced_10000_submission_$(date +%Y%m%d_%H%M%S).txt"
{
  echo "submitted_at=$(date --iso-8601=seconds)"
  echo "job_id=$job_id"
  echo "contract=10000 points; 2000 per state; reduced Random Forest; three endpoints; 2000-2025"
  echo "expected=8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/outputs/hpc_rf_reduced_10000_smoke/HPC_RF_REDUCED_10000_SMOKE_OK"
} | tee "$receipt"
echo "RF_REDUCED_10000_SUBMISSION_RECEIPT=$receipt"
