# Data placement

Large and third-party inputs are not committed to GitHub. A local working copy may use:

```text
data/
  station_year_model_matrix.parquet
  prediction_matrix.parquet
  covariates/
    <feature>.tif
```

Obtain ANADEM from its official source and record the version/checksum. ERA5-Land, MODIS and station observations must follow their respective access and redistribution terms. Final study outputs are distributed through the associated research-data repository rather than Git history.
