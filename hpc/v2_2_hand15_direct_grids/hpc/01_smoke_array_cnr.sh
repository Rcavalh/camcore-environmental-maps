#!/usr/bin/env bash
#BSUB -J "frostv22_smoke[1-4]%4"
#BSUB -q cnr
#BSUB -n 3
#BSUB -W 02:00
#BSUB -R "span[hosts=1] rusage[mem=8GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs/lsf_smoke.%J.%I.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs/lsf_smoke.%J.%I.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/hpc/runtime_env.sh
index=$((LSB_JOBINDEX - 1))
export FROST_OUTPUT="$FROST_MODULE/outputs/article_v2_2_direct_grids_hand15/five_states_smoke_2000_2026"
"$FROST_PYTHON_BIN" "$FROST_MODULE/scripts/60_hpc_predict_direct_climate_sc_lages_four_endpoints.py" --start-year 2000 --end-year 2026 --period-label ALL_2000_2026 --enso-csv "$FROST_ENSO_CSV" --bounds -58.1687892556576 -33.751232360358884 -44.16126919885123 -17.16626609035636 --label FIVE_STATES_HAND15 --input-labels PR_SC RS SP MS --input-dir "$FROST_DIRECT_INPUT" --output-dir "$FROST_OUTPUT" --tile-size 512 --model-workers 3 --shard-index "$index" --shard-count 4 --max-tiles 1
echo "ARTICLE_V2_2_HAND15_SMOKE_OK=$index"
