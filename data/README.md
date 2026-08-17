# Data included in the repository

## Model-ready Random Forest matrix

`model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv` is the canonical post-imputation station-season matrix used to refit the final HAND15 Random Forest. It contains:

- 2,693 eligible station-seasons from 219 INMET stations in five states;
- observed response years 2001-2026 within the requested 2000-2026 mapping period;
- the three response columns `frost_any`, `frost_days` and `observed_season_tmin_c`;
- exactly the 115 ordered predictors used by the production model;
- station identifiers and names needed to reproduce station-held-out validation.

The matrix excludes company frost-damage observations, unused candidate predictors, fitted values and proprietary data. Its companion `model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026_RAW.csv` deliberately retains missing predictor values so median imputation can be estimated from training data within each validation fold.

`../metadata/FINAL_BLOCK_BALANCED_FEATURES.csv` records feature order and block. `model_matrix/RF_MODEL_INPUT_HAND15_V2_PROVENANCE.json` records checksums, dimensions, missingness and identity with the model and script uploaded to HPC.

## Large inputs

Large rasters and third-party source archives are not committed to GitHub. Obtain ANADEM, ERA5-Land, MODIS and INMET data from their providers and respect their redistribution terms. Authoritative analytical GeoTIFF outputs are distributed through the associated Zenodo record rather than Git history.
