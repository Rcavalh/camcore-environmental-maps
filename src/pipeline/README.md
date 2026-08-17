# Frozen production scripts

This directory preserves the evolving scripts used to construct the five-state environmental database, fit candidate models, run reduced-scale checks, predict the native grid, merge shards and produce interpretation figures.

Important distinctions:

- These files preserve historical execution names and relative project assumptions for provenance.
- Some filenames contain `smoke`, the conventional software term used during development.
- New workstation users should start with `local/python` or `local/R`, which are portable and independent of the original directory tree.
- The final production model is the 115-predictor Random Forest refitted with 15 km HAND support. Final mapping uses direct annual ERA5-Land/MODIS grids rather than station IDW and applies no post-prediction smoothing. The corresponding fitting and mapping scripts are `63_validate_train_hand15_rf_tabpfn_2000_2026.py` and `60_hpc_predict_direct_climate_sc_lages_four_endpoints.py`. Scripts for XGBoost and TabPFN are retained as documented model-comparison experiments, not as dependencies of the final RF raster workflow.

The numeric prefixes record the approximate execution order. Consult `docs/REPRODUCIBILITY.md` before reusing individual files outside the original project structure.
