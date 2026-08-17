#!/usr/bin/env bash
#BSUB -J "frostv22_default[49-96]%20"
#BSUB -n 3
#BSUB -W 24:00
#BSUB -R "span[hosts=1] rusage[mem=8GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs/lsf_full_default.%J.%I.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs/lsf_full_default.%J.%I.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/hpc/runtime_env.sh
index=$((LSB_JOBINDEX - 1))
"$FROST_PYTHON_BIN" "$FROST_MODULE/scripts/60_hpc_predict_direct_climate_sc_lages_four_endpoints.py" --start-year 2000 --end-year 2026 --period-label ALL_2000_2026 --enso-csv "$FROST_ENSO_CSV" --bounds -58.1687892556576 -33.751232360358884 -44.16126919885123 -17.16626609035636 --label FIVE_STATES_HAND15 --input-labels PR_SC RS SP MS --input-dir "$FROST_DIRECT_INPUT" --output-dir "$FROST_OUTPUT" --tile-size 512 --model-workers 3 --shard-index "$index" --shard-count 96
echo "ARTICLE_V2_2_HAND15_DEFAULT_SHARD_OK=$index"
