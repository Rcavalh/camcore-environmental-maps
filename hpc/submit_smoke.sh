#!/usr/bin/env bash
set -euo pipefail
project_dir="${1:-$PWD}"
cd "$project_dir"
base="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf"
source "$base/hpc/runtime_env.sh"
mkdir -p "$base/logs"
job_id() { sed -n 's/.*Job <\([0-9]*\)>.*/\1/p'; }
preflight=$(bsub < "$base/hpc/00_preflight_cnr.sh" | job_id)
smoke=$(bsub -w "done(${preflight})" < "$base/hpc/01_smoke_array_cnr.sh" | job_id)
receipt="$base/logs/smoke_submission_$(date +%Y%m%d_%H%M%S).txt"
{
  echo "submitted_at=$(date --iso-8601=seconds)"
  echo "preflight_job_id=$preflight"
  echo "smoke_array_job_id=$smoke"
  echo "expected=HPC_SMOKE_SHARD_OK (four array elements)"
} | tee "$receipt"
echo "SMOKE_SUBMISSION_RECEIPT=$receipt"
