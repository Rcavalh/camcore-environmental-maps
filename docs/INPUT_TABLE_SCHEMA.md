# Portable input-table schema

The local Python and R workflows operate on a prepared station-year table. Each row represents one station and one eligible frost season.

## Required identifiers and endpoints

| Column | Type | Description |
|---|---|---|
| `station_id` | string | Stable station identifier used for grouped validation |
| `year` | integer | Frost-season year; also present in the feature manifest |
| `frost_any` | 0/1 | Whether at least one observed frost occurred in the eligible season |
| `frost_days` | non-negative numeric | Observed number of frost days in the eligible season |
| `observed_season_tmin_c` | numeric | Observed seasonal minimum temperature in degrees Celsius |

Optional descriptive columns such as station name and state are preserved in output tables but not used unless included in the versioned feature manifest.

## Predictors

Every column listed in `metadata/FINAL_BLOCK_BALANCED_FEATURES.csv` is required. The frozen production contract currently contains 115 predictors. Columns may contain missing values; the portable workflows fit median imputation using training data only.

## Prediction table

A tabular prediction matrix must contain the same predictor columns but does not require endpoint columns. Native-grid raster prediction requires one aligned `<feature>.tif` per predictor, with identical CRS, extent, transform and shape.

The public repository should not contain restricted station observations. Deposit a de-identified or access-controlled table only when its source terms allow redistribution.
