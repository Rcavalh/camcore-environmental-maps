# Local execution

The local workflow is designed for a workstation and does not require LSF or an HPC cluster. It has two independent reference implementations:

- `python/frost_rf_local.py`: recommended portable implementation based on scikit-learn;
- `R/frost_rf_local.R`: pure-R implementation based on `ranger`.

Both implementations train frost-occurrence probability, expected frost days and seasonal minimum temperature from the prepared station-year matrix. Both use the versioned predictor manifest in `metadata/FINAL_BLOCK_BALANCED_FEATURES.csv`. The implementations are methodologically equivalent but are not expected to produce bitwise-identical trees because `ranger` and scikit-learn use different tree engines.

Use `--quick-check N` for a reduced-scale integration check before running the complete local analysis. Public documentation uses **reduced-scale integration check** or **preflight validation**. The historical term `smoke test` is valid in software engineering but is not presented as scientific model validation.

## Python

```bash
python -m venv .venv
python -m pip install -r local/python/requirements.txt
python local/python/frost_rf_local.py \
  --training data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv \
  --features metadata/FINAL_BLOCK_BALANCED_FEATURES.csv \
  --output outputs/local_python \
  --quick-check 10000
```

The Python workflow groups validation folds by `state + station_id` and uses the final 900-tree occurrence classifier and 700-tree regressors. Remove `--quick-check 10000` for the complete training run. Add `--prediction data/prediction_matrix.parquet` to produce tabular predictions.

The final production maps use the direct annual climate-grid procedure documented in [`../docs/REPRODUCIBILITY.md`](../docs/REPRODUCIBILITY.md). The simpler `predict_covariate_stack.py` utility applies when one aligned GeoTIFF already exists for every predictor.

## R

```bash
Rscript local/R/install_packages.R
Rscript local/R/frost_rf_local.R \
  --training=data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv \
  --features=metadata/FINAL_BLOCK_BALANCED_FEATURES.csv \
  --output=outputs/local_R \
  --group_column=station_id \
  --quick_check=10000
```
