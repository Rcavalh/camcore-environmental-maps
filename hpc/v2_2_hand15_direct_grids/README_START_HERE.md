# Article v2.2 — HAND 15 km, direct climate grids, 2000–2026

This package refits the reduced 115-predictor Random Forest after replacing the
2-km HAND flow-path search radius with 15 km at both meteorological stations and
map pixels. All model validation remains station-held-out. The requested climate
and mapping period is rigidly 2000–2026; the current observed INMET response
table contains eligible response seasons for 2001–2026, which is reported rather
than silently inventing a 2000 label.

Continuous ERA5-Land and MODIS grids are aligned bilinearly; discrete and count
grids use nearest-neighbour alignment. There is no station IDW and no
post-prediction smoothing. This is the direct-grid correction for the former
triangular climate artifacts.

The production outputs are the four complete-period rasters plus six
ENSO-conditioned rasters (probability and Tmin P25 for El Nino, La Nina and
Neutral), all based on climate years 2000–2026.

## Upload and extract

In the original Hazel run, four archives were extracted into a single project root. For a new cluster, set `FROST_PROJECT_ROOT` to that root and adapt the scheduler paths:

1. `HPC_ARTICLE_V2_1_INPUTS_PART1_PR_SC_CORE_20260815.zip`
   (PR-SC climate stacks plus shared code and configuration).
2. `HPC_ARTICLE_V2_1_INPUTS_PART2_RS_MS_20260815.zip`
   (RS and MS climate stacks).
3. `HPC_ARTICLE_V2_1_INPUTS_PART3_SP_20260815.zip`
   (SP climate stacks).
4. `HPC_ARTICLE_V2_2_HAND15_2000_2026_INCREMENTAL_20260815.zip`
   (HAND 15 km, refitted Random Forest, scripts, metrics and station keys).

The first three ZIP files jointly contain the same 432 direct annual
ERA5-Land/MODIS stacks as the former single large input archive. Each ZIP is
independently extractable and below the 10-GB upload limit.

Then run:

```bash
cd <FROST_PROJECT_ROOT>
unzip -o HPC_ARTICLE_V2_1_INPUTS_PART1_PR_SC_CORE_20260815.zip
unzip -o HPC_ARTICLE_V2_1_INPUTS_PART2_RS_MS_20260815.zip
unzip -o HPC_ARTICLE_V2_1_INPUTS_PART3_SP_20260815.zip
unzip -o HPC_ARTICLE_V2_2_HAND15_2000_2026_INCREMENTAL_20260815.zip
```

## Submit

```bash
cd <FROST_PROJECT_ROOT>
hpc="8.Dados_Meteorologicos_Publicos/08_Five_State_Environmental_Integration/hpc_article_v2_2_direct_grids_hand15_2000_2026"
bash "$hpc/hpc/submit_full_split_after_smoke.sh" "$PWD"
```

Use the three printed job IDs to monitor:

```bash
bash "$hpc/hpc/status.sh" CNR_ARRAY_JOB DEFAULT_ARRAY_JOB MERGE_JOB
```

The incremental ZIP uses the 432 annual climate stacks extracted from the first
ZIP at `hpc_article_v2_0_direct_grids_five_states/inputs/climate_annual`.
Preflight checks all four stacks for all four state groups and every year from
2000 through 2026 before any smoke or production shard starts.
