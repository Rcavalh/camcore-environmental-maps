# Frozen production scripts

This directory preserves the evolving scripts used to construct the five-state environmental database, fit candidate models, run reduced-scale checks, predict the native grid, merge shards and produce interpretation figures.

Important distinctions:

- These files preserve historical execution names and relative project assumptions for provenance.
- Some filenames contain `smoke`, the conventional software term used during development.
- New workstation users should start with `local/python` or `local/R`, which are portable and independent of the original directory tree.
- The final production model is the reduced, block-balanced Random Forest. Scripts for XGBoost and TabPFN are retained as documented model-comparison experiments, not as dependencies of the final RF raster workflow.

The numeric prefixes record the approximate execution order. Consult `docs/REPRODUCIBILITY.md` before reusing individual files outside the original project structure.
