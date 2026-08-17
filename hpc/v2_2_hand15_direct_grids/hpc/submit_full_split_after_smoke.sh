#!/usr/bin/env bash
set -euo pipefail
cd "${1:-$PWD}"
hpc="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026"
preflight=$(bsub < "$hpc/hpc/00_preflight_cnr.sh" | sed -n 's/.*Job <\([0-9]*\)>.*/\1/p')
smoke=$(bsub -w "done($preflight)" < "$hpc/hpc/01_smoke_array_cnr.sh" | sed -n 's/.*Job <\([0-9]*\)>.*/\1/p')
cnr_array=$(bsub -w "done($smoke)" < "$hpc/hpc/02a_full_array_cnr_half.sh" | sed -n 's/.*Job <\([0-9]*\)>.*/\1/p')
default_array=$(bsub -w "done($smoke)" < "$hpc/hpc/02b_full_array_default_half.sh" | sed -n 's/.*Job <\([0-9]*\)>.*/\1/p')
merge=$(bsub -w "done($cnr_array) && done($default_array)" < "$hpc/hpc/03_merge_cnr.sh" | sed -n 's/.*Job <\([0-9]*\)>.*/\1/p')
echo "preflight_job_id=$preflight"
echo "smoke_array_job_id=$smoke elements=4"
echo "cnr_array_job_id=$cnr_array global_shards=0-47 max_concurrent=20"
echo "default_array_job_id=$default_array global_shards=48-95 max_concurrent=20"
echo "merge_job_id=$merge"
echo "contract=HAND 15 km; RF refitted; direct ERA5-Land and MODIS grids; 2000-2026; 10 rasters; no post-prediction smoothing"
echo "expected=8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/outputs/article_v2_2_direct_grids_hand15/five_states_all_2000_2026/ARTICLE_V2_2_HAND15_DIRECT_GRIDS_10MAPS_MERGE_OK"
