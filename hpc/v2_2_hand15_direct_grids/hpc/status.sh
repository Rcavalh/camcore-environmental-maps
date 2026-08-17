#!/usr/bin/env bash
set -euo pipefail
cnr_job="${1:-}"
default_job="${2:-}"
merge_job="${3:-}"
root="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/outputs/article_v2_2_direct_grids_hand15/five_states_all_2000_2026"
logs="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026/logs"
echo "--- HAND15 / PERIOD CONTRACT ---"
echo "HAND flow-path radius=15000 m | climate period=2000-2026 | rasters=10"
echo "--- CNR HALF ---"
[[ -n "$cnr_job" ]] && bjobs -A -w "$cnr_job" 2>/dev/null || true
echo "--- DEFAULT-QUEUE HALF ---"
[[ -n "$default_job" ]] && bjobs -A -w "$default_job" 2>/dev/null || true
tiles=$(find "$root/shards_512" -mindepth 3 -maxdepth 3 -type f -path '*/checkpoints/tile_*.json' 2>/dev/null | wc -l)
shards=$(find "$root/shards_512" -mindepth 2 -maxdepth 2 -type f -name 'SHARD_*_OF_96_OK' 2>/dev/null | wc -l)
echo "--- PROGRESS ---"
echo "tiles=$tiles/12342"
echo "shards=$shards/96"
echo "--- ERRORS ---"
grep -HnE '^Traceback|RasterioIOError|MemoryError|Killed|TERM_|TIME LIMIT' "$logs"/*.err 2>/dev/null | tail -20 || true
echo "--- MERGE ---"
[[ -n "$merge_job" ]] && bjobs -a "$merge_job" 2>/dev/null || true
echo "--- FINAL ---"
test -f "$root/ARTICLE_V2_2_HAND15_DIRECT_GRIDS_10MAPS_MERGE_OK" && echo COMPLETE || echo PROCESSING
