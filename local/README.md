# Local execution / Execução local

## English

The local workflow is designed for a workstation and does not require LSF or an HPC cluster. It has two independent reference implementations:

- `python/frost_rf_local.py`: exact scikit-learn-style three-endpoint workflow used as the recommended portable implementation.
- `R/frost_rf_local.R`: pure-R `ranger` implementation for users who work primarily in R.

Both train frost-occurrence probability, expected frost days and seasonal minimum temperature from a prepared station-year matrix. Both accept the versioned feature manifest in `metadata/FINAL_BLOCK_BALANCED_FEATURES.csv`. The R and Python implementations are methodologically equivalent but are not expected to produce bitwise-identical trees because `ranger` and scikit-learn use different tree engines.

Use `--quick-check N` to run a reduced-scale integration check before the complete local analysis. In public documentation we use **reduced-scale integration check** or **preflight validation**. “Smoke test” remains a valid software-engineering term, but it should not be presented as a scientific validation result.

### Python

```bash
python -m venv .venv
python -m pip install -r local/python/requirements.txt
python local/python/frost_rf_local.py \
  --training data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv \
  --features metadata/FINAL_BLOCK_BALANCED_FEATURES.csv \
  --output outputs/local_python \
  --quick-check 10000
```

The Python workflow groups folds by `state + station_id` by default and uses the final 900-tree classifier and 700-tree regressors. Remove `--quick-check 10000` for the complete training run. Add `--prediction data/prediction_matrix.parquet` to generate tabular predictions. The final production maps used the direct annual climate-grid script documented in `docs/REPRODUCIBILITY.md`; the simpler `predict_covariate_stack.py` applies when one aligned GeoTIFF already exists per predictor.

### R

```bash
Rscript local/R/install_packages.R
Rscript local/R/frost_rf_local.R \
  --training=data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv \
  --features=metadata/FINAL_BLOCK_BALANCED_FEATURES.csv \
  --output=outputs/local_R \
  --group_column=station_id \
  --quick_check=10000
```

## Português

O fluxo local foi preparado para uma estação de trabalho e não exige LSF nem cluster. Há duas implementações independentes:

- `python/frost_rf_local.py`: implementação portátil recomendada, baseada no scikit-learn.
- `R/frost_rf_local.R`: implementação integral em R com o pacote `ranger`.

As duas treinam probabilidade de ocorrência, número esperado de dias de geada e temperatura mínima sazonal a partir da matriz estação–ano. O manifesto de preditores é `metadata/FINAL_BLOCK_BALANCED_FEATURES.csv`.

Use `--quick-check` para a verificação reduzida antes da execução completa. Nos textos científicos, prefira **verificação de integração em escala reduzida** ou **validação prévia**. “Smoke test” é correto em engenharia de software, mas não deve ser descrito como validação científica do modelo.
