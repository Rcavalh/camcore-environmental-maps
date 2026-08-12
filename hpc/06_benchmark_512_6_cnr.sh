#!/usr/bin/env bash
#BSUB -J frost5_bench_512x6
#BSUB -q cnr
#BSUB -n 6
#BSUB -W 02:00
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem=12GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_bench_512x6.%J.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/logs/lsf_bench_512x6.%J.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_full_native_rf/hpc/runtime_env.sh
export FROST_OUTPUT="$FROST_MODULE/outputs/hpc_optimization_benchmark/tile512_cpu6"
export FROST_SCENARIO_SET=all
export FROST_TMIN_AGGREGATION=p25
export FROST_YEAR_WORKERS=6
export FROST_MODEL_WORKERS=1
export FROST_PREDICTION_CHUNK=90000
export FROST_FLUSH_EVERY=20
export FROST_ZSTD_LEVEL=1
"$FROST_PYTHON_BIN" "$FROST_MODULE/scripts/29_predict_full_native_balanced_rf.py" \
  --tile-size 512 --shard-index 0 --shard-count 1 --max-valid-tiles 4
echo "HPC_OPTIMIZATION_BENCHMARK_OK=tile512_cpu6"
