# Hazel/LSF workflow archive

These scripts record the exact submission pattern used for the five-state native-grid Random Forest production run. They are retained for provenance and adaptation, not as a universal one-command deployment.

Before reuse:

1. set `FROST_PROJECT_ROOT`, `FROST_MODULE`, `FROST_PYTHON_BIN`, `FROST_HPC_INPUT`, `FROST_MODEL` and `FROST_ENSO` in the job environment;
2. update the `#BSUB -o/-e` paths for the destination cluster;
3. generate a machine-specific `source_roots_hpc.json` from the public configuration example;
4. run preflight and the 10,000-cell reduced-scale integration check before full submission (historical filenames retain `smoke`);
5. verify input GeoTIFF checksums, especially HAND, before launching array jobs.

The historical scripts assume the original project module layout. The Python implementation they call is preserved in `src/pipeline/`.

## Public terminology

| Purpose | Preferred term | Historical script pattern |
|---|---|---|
| Package/input checks | Preflight validation | `00_preflight_*` |
| Small end-to-end execution | Reduced-scale integration check | `*smoke*` |
| Full tiled prediction | Production run | `*full*`, `*all_period*` |
| Shard combination and QC | Merge and raster audit | `*merge*`, final markers |

Do not report the reduced-scale integration check as model validation. Scientific validation metrics come from held-out grouped/spatial folds.
