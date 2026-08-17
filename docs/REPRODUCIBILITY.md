# Reproducibility guide

## 1. Current production version

Use the **v2.2 HAND15 direct-grid** contract for the published frost maps. Older scripts remain in the repository only to preserve analytical provenance.

Key invariants are:

- climate mapping period: 2000-2026;
- observed response period: 2001-2026;
- frost-season window: 15 May-15 August;
- 115 ordered predictors;
- HAND downstream flow-path support: 15 km;
- other local terrain summaries: 2 km;
- direct annual ERA5-Land/MODIS grids, with no station IDW;
- no post-prediction smoothing.

## 2. Refit the three Random Forest endpoints locally

Create the Python environment and run:

```bash
python local/python/frost_rf_local.py \
  --training data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv \
  --features metadata/FINAL_BLOCK_BALANCED_FEATURES.csv \
  --output outputs/local_rf_hand15
```

The command groups validation by `state + station_id` by default. The local implementation refits the frozen 115-feature production contract. The exact historical feature-selection and validation implementation is preserved in `src/pipeline/63_validate_train_hand15_rf_tabpfn_2000_2026.py`.

## 3. Reproduce direct-grid maps

The map-production implementation is preserved in `src/pipeline/60_hpc_predict_direct_climate_sc_lages_four_endpoints.py`. It requires:

1. the ANADEM mosaic and aligned 15 km HAND raster;
2. the fitted Random Forest bundle;
3. four annual stack types (ERA5 continuous/count and MODIS continuous/count) for each state group and year;
4. the frozen ENSO-year table when ENSO products are requested.

The production script aligns continuous stacks bilinearly and count/discrete stacks by nearest neighbour, predicts 512 x 512 tiles, writes persistent shard outputs and never uses station IDW. The LSF submission pattern and merge checks are documented in `hpc/README.md`.

The GRASS workflow that derives the 15 km HAND layer is documented and preserved in [`src/hand15`](../src/hand15/README.md).

## 4. Validation stages

1. **Preflight validation:** verify packages, input presence, raster readability, model contract and checksums.
2. **Reduced-scale integration check:** process a small spatial sample and confirm export of every endpoint.
3. **Scientific validation:** calculate held-out station-grouped cross-validation metrics.
4. **Production prediction:** process every native-grid tile.
5. **Merge and audit:** combine completed shards and verify CRS, transform, NoData, value range, coverage and checksums.

Historical filenames may contain `smoke`; public documentation uses “reduced-scale integration check” so it is not confused with scientific validation.

## 5. Data and feature contracts

- [`data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv`](../data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv): exact post-imputation matrix used for the final all-data production refit; 2,693 station-season rows, identifiers, three responses and 115 ordered predictors.
- [`data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026_RAW.csv`](../data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026_RAW.csv): pre-imputation companion required for fold-wise imputation during grouped validation.
- [`metadata/FINAL_BLOCK_BALANCED_FEATURES.csv`](../metadata/FINAL_BLOCK_BALANCED_FEATURES.csv): ordered predictor list and scientific block.
- [`data/model_matrix/RF_MODEL_INPUT_HAND15_V2_PROVENANCE.json`](../data/model_matrix/RF_MODEL_INPUT_HAND15_V2_PROVENANCE.json): dimensions, period, checksums, missingness and HPC model/script identity audit.

Missing predictor cells in the raw companion are intentional. Do not pre-impute that raw matrix before grouped validation: the imputer must be fitted independently from each set of training folds. The canonical matrix is already imputed and is intended only to reproduce the final all-data production refit.

## 6. Completion contract

A scheduler status of `DONE` is insufficient. Completion requires all endpoint files, final markers, raster audits and checksums. Development previews and reduced-scale outputs are excluded from the scientific deposit.
