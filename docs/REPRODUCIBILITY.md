# Reproducibility guide

## 1. Choose an execution path

### Local Python — recommended exact portable workflow

Use `local/python/frost_rf_local.py` to train and spatially validate the three endpoints from a prepared station-year matrix. Use `local/python/predict_covariate_stack.py` when every model feature is available as an aligned GeoTIFF.

### Local R — independent reference implementation

Use `local/R/frost_rf_local.R` and `local/R/predict_covariate_stack.R`. This workflow follows the same endpoint and predictor contract using `ranger` and `terra`. It is methodologically equivalent, but numerical results are not bitwise identical to scikit-learn.

### HPC Python — production native-grid workflow

The `hpc/` directory contains the LSF job-array and merge scripts used for the five-state run. The exact historical analysis scripts are retained under `src/pipeline/`. Configure machine paths through environment variables and `config/source_roots.example.json`; never commit private absolute paths.

## 2. Validation stages

1. **Preflight validation:** verifies packages, input presence, raster readability, model contract and checksums.
2. **Reduced-scale integration check:** processes a small, spatially distributed sample and confirms that all three endpoints can be exported.
3. **Scientific validation:** reports held-out grouped or spatial cross-validation metrics.
4. **Production prediction:** processes every native-grid tile.
5. **Merge and audit:** combines completed shards and verifies CRS, transform, NoData, range, coverage and checksum.

The historical implementation uses `smoke` in some filenames and completion markers. This is preserved for traceability; manuscripts and user-facing documentation should use the stage names above.

## 3. Predictor contract

`metadata/FINAL_BLOCK_BALANCED_FEATURES.csv` is the machine-readable source of truth. Do not manually infer predictor lists from prose. A run must stop if any required predictor is missing or duplicated.

## 4. Randomness and parallelism

- Preserve the documented random seed.
- Record software versions and the feature-manifest checksum.
- The same implementation and input snapshot should be used for formal comparison.
- Different Random Forest engines, thread counts or library versions may produce small numerical differences.

## 5. Completion contract

A run is not complete merely because a scheduler reports `DONE`. Completion requires endpoint files, final markers, raster audits and checksums. Development previews and reduced-scale integration outputs are excluded from the scientific deposit.
