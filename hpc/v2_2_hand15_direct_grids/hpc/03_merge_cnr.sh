#!/usr/bin/env bash
#BSUB -J frostv22_merge
#BSUB -q cnr
#BSUB -n 4
#BSUB -W 12:00
#BSUB -R "span[hosts=1] rusage[mem=12GB]"
#BSUB -o 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs/lsf_merge.%J.out
#BSUB -e 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs/lsf_merge.%J.err
set -euo pipefail
source 8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/hpc/runtime_env.sh
"$FROST_PYTHON_BIN" "$FROST_MODULE/scripts/30_merge_full_native_balanced_rf_shards.py" --tile-size 512 --shard-count 96
test -f "$FROST_OUTPUT/$FROST_MERGE_MARKER"
test "$(find "$FROST_OUTPUT/rasters_final" -maxdepth 1 -type f -name '*.tif' | wc -l)" -eq 10
echo "ARTICLE_V2_2_HAND15_DIRECT_GRIDS_10MAPS_MERGE_OK"
