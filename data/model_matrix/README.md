# Random Forest model input — version 2.0

`RF_MODEL_INPUT_V2_2001_2026.csv` is the official version 2.0 Random Forest
model-input matrix extracted from the `V2 Model Input` worksheet of
`RF_MODEL_INPUT_COMPLETE_V1_V2.xlsx`. The version 1 worksheet is not included
in this repository.

## Contents

- 2,693 eligible station-season records;
- 219 INMET stations;
- observed response years 2001–2026 within the 2000–2026 climate-mapping
  period;
- four identifiers, three observed responses and 115 ordered predictors;
- 19 terrain/HAND/space/time, 64 ERA5-Land and 32 MODIS predictors.

The three response columns are `frost_any`, `frost_days` and
`observed_season_tmin_c`. Company-damage observations are not included.

## Important processing distinction

This public table is the complete **post-imputation production-bundle input**.
Consequently, its 115 predictor columns contain no blank cells. This does not
mean that every raw satellite retrieval was observed. In the source audit,
83.1775% of selected raw MODIS cells were observed and no station-season was
missing the complete selected MODIS block. Missing raw predictor values were
replaced by the frozen full-data median imputer used to fit the production
bundle.

For station-grouped cross-validation, the imputer was not transferred from
the full dataset: the imputer and Random Forest were refitted separately using
the training stations in each fold. This separation prevents validation data
from contributing to fold-wise imputation.

## Integrity

`RF_MODEL_INPUT_V2_PROVENANCE.json` records the source workbook checksum, CSV
checksum, dimensions, model-bundle checksum and the verified SHA-256 digest of
the ordered float32 predictor matrix. The latter exactly matches the value
reported in the source workbook's `Audit Summary` worksheet.
