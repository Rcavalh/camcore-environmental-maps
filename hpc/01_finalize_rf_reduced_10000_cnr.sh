#!/usr/bin/env bash
#BSUB -J frost5_rf10k_finalize
#BSUB -q cnr
#BSUB -n 4
#BSUB -W 00:30
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem=16GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_rf10k_finalize.%J.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_rf10k_finalize.%J.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/hpc/runtime_env.sh
export FROST_SMOKE_OUTPUT="$FROST_MODULE/outputs/hpc_rf_reduced_10000_smoke"
"$FROST_PYTHON_BIN" "$FROST_MODULE/scripts/35_finalize_hpc_rf_reduced_10000_smoke.py"
echo "HPC_RF_REDUCED_10000_FINALIZE_OK"
