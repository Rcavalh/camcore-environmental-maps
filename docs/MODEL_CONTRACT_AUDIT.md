# Reduced Random Forest contract audit

## Verified production contract

The frozen `RF_BLOCK_BALANCED_ALL_ENDPOINTS` bundle reports **115 predictors**:

| Block | Predictors |
|---|---:|
| Terrain, HAND, space and year | 19 |
| ERA5-Land | 64 |
| MODIS | 32 |
| **Total** | **115** |

The authoritative names are stored in `metadata/FINAL_BLOCK_BALANCED_FEATURES.csv`; the summary is stored in `metadata/RF_REDUCED_MODEL_CONTRACT.json`.

## Manuscript implication

An earlier methods draft described a 49-variable model comprising 2 coordinates, 17 terrain/HAND, 21 ERA5-Land and 9 MODIS variables. That text does **not** describe the current frozen 115-feature production bundle. Before publication, choose one of two defensible options:

1. update the methods table and predictor supplement to the verified 115-feature contract; or
2. retrain and freeze a genuine 49-feature model, rerun validation and regenerate every mapped product.

Do not combine the 49-variable prose with metrics or rasters produced by the 115-feature bundle. “Reduced” means reduced relative to the much larger candidate feature pool, not restricted to 49 predictors.
