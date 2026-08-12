#!/usr/bin/env bash
set -euo pipefail
project_dir="${1:-$PWD}"
cd "$project_dir"
base="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf"
source "$base/hpc/runtime_env.sh"
mkdir -p "$base/logs"
job_id() { sed -n 's/.*Job <\([0-9]*\)>.*/\1/p'; }
preflight=$(bsub < "$base/hpc/00_preflight_cnr.sh" | job_id)
full=$(bsub -w "done(${preflight})" < "$base/hpc/02_full_array_cnr.sh" | job_id)
merge=$(bsub -w "done(${full})" < "$base/hpc/03_merge_cnr.sh" | job_id)
receipt="$base/logs/full_submission_$(date +%Y%m%d_%H%M%S).txt"
{
  echo "submitted_at=$(date --iso-8601=seconds)"
  echo "preflight_job_id=$preflight"
  echo "full_array_job_id=$full"
  echo "merge_job_id=$merge"
  echo "array=96 shards; maximum 48 concurrent"
  echo "expected=$FROST_PROJECT_ROOT/8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/outputs/hpc_full_native_balanced_rf/FULL_NATIVE_BALANCED_RF_MERGE_OK"
} | tee "$receipt"
echo "FULL_SUBMISSION_RECEIPT=$receipt"
