#!/usr/bin/env bash
set -euo pipefail
project_dir="${1:-$PWD}"
cd "$project_dir"
base="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf"
source "$base/hpc/runtime_env.sh"
mkdir -p "$base/logs"
job_id() { sed -n 's/.*Job <\([0-9]*\)>.*/\1/p'; }
preflight=$(bsub < "$base/hpc/00_preflight_cnr.sh" | job_id)
full=$(bsub -w "done(${preflight})" < "$base/hpc/02_all_period_array_cnr.sh" | job_id)
merge=$(bsub -w "done(${full})" < "$base/hpc/03_merge_all_period_cnr.sh" | job_id)
receipt="$base/logs/all_period_submission_$(date +%Y%m%d_%H%M%S).txt"
{
  echo "submitted_at=$(date --iso-8601=seconds)"
  echo "preflight_job_id=$preflight"
  echo "all_period_array_job_id=$full"
  echo "merge_job_id=$merge"
  echo "contract=Random Forest reduced; 2000-2025 mean; probability + frost days + seasonal minimum temperature"
  echo "array=96 shards; maximum 8 concurrent"
  echo "expected=$FROST_MODULE/outputs/hpc_full_native_balanced_rf_all_2000_2025/FULL_NATIVE_BALANCED_RF_MERGE_OK"
} | tee "$receipt"
echo "ALL_PERIOD_SUBMISSION_RECEIPT=$receipt"
