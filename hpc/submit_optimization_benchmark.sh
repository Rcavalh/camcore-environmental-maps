#!/usr/bin/env bash
set -euo pipefail
project_dir="${1:-$PWD}"
cd "$project_dir"
base="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf"
mkdir -p "$base/logs"
job_id() { sed -n 's/.*Job <\([0-9]*\)>.*/\1/p'; }
j512=$(bsub < "$base/hpc/06_benchmark_512_6_cnr.sh" | job_id)
j1024x6=$(bsub < "$base/hpc/06_benchmark_1024_6_cnr.sh" | job_id)
j1024x4=$(bsub < "$base/hpc/06_benchmark_1024_4_cnr.sh" | job_id)
receipt="$base/logs/optimization_benchmark_submission_$(date +%Y%m%d_%H%M%S).txt"
{
  echo "submitted_at=$(date --iso-8601=seconds)"
  echo "tile512_cpu6_job_id=$j512"
  echo "tile1024_cpu6_job_id=$j1024x6"
  echo "tile1024_cpu4_job_id=$j1024x4"
  echo "comparison=approximately one million valid pixels per configuration"
  echo "scientific_contract=identical model, covariates, years, scenarios and P25 aggregation"
} | tee "$receipt"
echo "HPC_OPTIMIZATION_BENCHMARK_RECEIPT=$receipt"
