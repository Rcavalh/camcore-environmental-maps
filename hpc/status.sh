#!/usr/bin/env bash
set -euo pipefail
base="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf"
receipt=$(ls -t "$base"/logs/full_submission_*.txt 2>/dev/null | head -1 || true)
if [[ -z "$receipt" ]]; then
  receipt=$(ls -t "$base"/logs/smoke_submission_*.txt 2>/dev/null | head -1 || true)
fi
[[ -n "$receipt" ]] || { echo "No submission receipt found"; exit 1; }
cat "$receipt"
ids=$(awk -F= '/_job_id=/{printf "%s ",$2}' "$receipt")
echo "--- LSF status ---"
bjobs -a $ids 2>/dev/null || true
echo "--- completed shards ---"
find 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/outputs/hpc_full_native_balanced_rf/shards_512 \
  -type f -name 'SHARD_*_OK' 2>/dev/null | wc -l
echo "--- final marker ---"
find 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/outputs/hpc_full_native_balanced_rf \
  -maxdepth 1 -type f -name 'FULL_NATIVE_BALANCED_RF_MERGE_OK' -print 2>/dev/null || true
