# Portable input-table schema

The local Python and R workflows operate on a prepared station-year table. Each row represents one station and one eligible frost season.

## Required identifiers and endpoints

| Column | Type | Description |
|---|---|---|
| `state` | string | State code; combined with `station_id` for grouped validation |
| `station_id` | string | Stable station identifier; all years from a station remain in the same fold |
| `year` | integer | Frost-season year; also present in the feature manifest |
| `frost_any` | 0/1 | Whether at least one observed frost occurred in the eligible season |
| `frost_days` | non-negative numeric | Observed number of frost days in the eligible season |
| `observed_season_tmin_c` | numeric | Observed seasonal minimum temperature in degrees Celsius |

Optional descriptive columns such as station name are preserved in output tables. Scientific validation uses the composite key `state + station_id`.

## Predictors

Every column listed in `metadata/FINAL_BLOCK_BALANCED_FEATURES.csv` is required. The frozen production contract currently contains 115 predictors. Columns may contain missing values; the portable workflows fit median imputation using training data only.

## Prediction table

A tabular prediction matrix must contain the same predictor columns but does not require endpoint columns. Native-grid raster prediction requires one aligned `<feature>.tif` per predictor, with identical CRS, extent, transform and shape.

The included public matrix contains INMET-derived station-season responses and public environmental covariates. It excludes company damage observations and other restricted data.
