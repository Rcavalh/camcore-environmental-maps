#!/usr/bin/env bash
#BSUB -J "frost5_full[1-96]%48"
#BSUB -q cnr
#BSUB -n 8
#BSUB -W 12:00
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem=32GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_full.%J.%I.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_full.%J.%I.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/hpc/runtime_env.sh
export FROST_YEAR_WORKERS=6
export FROST_MODEL_WORKERS=1
export FROST_PREDICTION_CHUNK=90000
index=$((LSB_JOBINDEX - 1))
"$FROST_PYTHON_BIN" "$FROST_MODULE/scripts/29_predict_full_native_balanced_rf.py" \
  --tile-size 512 --shard-index "$index" --shard-count 96
echo "HPC_FULL_SHARD_OK=$index"
