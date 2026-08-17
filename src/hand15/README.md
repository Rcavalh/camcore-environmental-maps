# Reproducing the 15 km HAND layer

These files preserve the GRASS GIS workflow used for the final five-state HAND layer. The input is the continuous ANADEM mosaic at its native approximately 30 m grid.

The production contract uses:

- drainage-network initiation threshold: 2,000 contributing cells;
- downstream flow-path support radius: 15,000 m;
- GRASS `r.watershed` drainage direction followed by `r.stream.distance` HAND calculation;
- no interpolation or post-processing smoothing of valid HAND values.

The two numeric parameters serve different purposes. The 2,000-cell threshold controls derived drainage density. The 15 km radius controls how far a terrain cell may be connected downstream to that drainage network.

Example:

```bash
export HAND_FLOWPATH_RADII_M="15000"
export HAND_EXPORT_FILLED_ZERO=1
export HAND_WATERSHED_DISK_SWAP=1
export HAND_STUDENT_EXACT=1

bash src/hand15/grass_hand_native.sh \
  --dem /path/to/anadem_five_state_mosaic.tif \
  --output-dir /path/to/hand15_output \
  --label anadem_rs_pr_sc_sp_ms_30m \
  --stream-threshold-cells 2000 \
  --memory-mb 300000
```

The filled-zero export is convenient for raster storage, but zero denotes unresolved support in this workflow. The station/model code therefore converts non-finite and non-positive sampled HAND values back to missing before fold-wise median imputation. Do not treat every stored zero as a measured valley-bottom HAND of zero metres.

Run `validate_multistate_hand.R` before accepting the output. The expected scientific raster is `anadem_rs_pr_sc_sp_ms_30m_HAND_flowpath_within_15000m.tif`; the filled-zero companion is an operational input whose special zero semantics must be retained.
