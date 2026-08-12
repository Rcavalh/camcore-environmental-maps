#!/usr/bin/env bash
#BSUB -J frost5_all_merge
#BSUB -q cnr
#BSUB -n 4
#BSUB -W 12:00
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem=32GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_all_period_merge.%J.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_all_period_merge.%J.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/hpc/runtime_env.sh
export FROST_OUTPUT="$FROST_MODULE/outputs/hpc_full_native_balanced_rf_all_2000_2025"
export FROST_EXPECTED_RASTERS=3
"$FROST_PYTHON_BIN" "$FROST_MODULE/scripts/30_merge_full_native_balanced_rf_shards.py" \
  --tile-size 512 --shard-count 96
echo "HPC_ALL_PERIOD_MERGE_OK"
