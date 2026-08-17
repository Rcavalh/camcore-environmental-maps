# Final Random Forest HAND15 model input — version 2.0

`RF_MODEL_INPUT_HAND15_V2_2001_2026.csv` is the canonical model-input matrix
consumed by the final Random Forest HAND15 production bundle used in the HPC
article-v2.2 mapping workflow.

## Contents

- 2,693 eligible station-season records from 219 INMET stations;
- observed response years 2001–2026 within the 2000–2026 climate-mapping
  period;
- four identifiers, three observed responses and 115 ordered predictors;
- 19 spatial/terrain/HAND/time, 64 ERA5-Land and 32 MODIS predictors;
- HAND calculated with a maximum 15,000-m downstream flow-path search.

The response columns are `frost_any`, `frost_days` and
`observed_season_tmin_c`. Company-damage observations are not included.

## Canonical and raw matrices

- `RF_MODEL_INPUT_HAND15_V2_2001_2026.csv` contains the exact post-imputation
  float32 predictor matrix passed to the final production models. It is the
  appropriate file for reproducing the final all-data model refit.
- `RF_MODEL_INPUT_HAND15_V2_2001_2026_RAW.csv` preserves missing predictor
  values. It is the appropriate starting point for station-grouped
  cross-validation, because the median imputer must be fitted independently
  using only the training stations in each fold.

The raw matrix contains 20,731 missing predictor cells; the canonical matrix
contains none after application of the stored production median imputer.

## Integrity and HPC identity

`RF_MODEL_INPUT_HAND15_V2_PROVENANCE.json` records dimensions, ordered
predictors, missingness, SHA-256 checksums and the hashes of the production
model and training script. The model and script hashes were verified against
the copies stored in
`HPC_ARTICLE_V2_2_HAND15_2000_2026_INCREMENTAL_20260815.zip`.
