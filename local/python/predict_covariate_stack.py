#!/usr/bin/env python
"""Predict three frost endpoints from a directory of aligned covariate GeoTIFFs."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from pathlib import Path

import joblib
import numpy as np
import rasterio
from rasterio.windows import Window


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--covariates", type=Path, required=True,
                   help="Directory containing one <feature>.tif per model feature")
    p.add_argument("--template", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--tile-size", type=int, default=512)
    args = p.parse_args()
    bundle = joblib.load(args.model)
    args.output.mkdir(parents=True, exist_ok=True)

    paths = {feature: args.covariates / f"{feature}.tif" for feature in bundle["features"]}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} covariate rasters; first: {missing[:5]}")

    output_names = {
        "probability": "RF_FROST_OCCURRENCE_PROBABILITY.tif",
        "frost_days": "RF_EXPECTED_FROST_DAYS.tif",
        "seasonal_tmin_c": "RF_SEASONAL_MINIMUM_TEMPERATURE_C.tif",
    }
    with ExitStack() as stack:
        template = stack.enter_context(rasterio.open(args.template))
        sources = {name: stack.enter_context(rasterio.open(path)) for name, path in paths.items()}
        for name, src in sources.items():
            if src.shape != template.shape or src.transform != template.transform or src.crs != template.crs:
                raise ValueError(f"Covariate is not aligned with template: {name}")
        profile = template.profile.copy()
        profile.update(dtype="float32", count=1, nodata=-9999.0, compress="DEFLATE",
                       tiled=True, blockxsize=512, blockysize=512, BIGTIFF="YES")
        outputs = {key: stack.enter_context(rasterio.open(args.output / name, "w", **profile))
                   for key, name in output_names.items()}

        total = ((template.height + args.tile_size - 1) // args.tile_size) * ((template.width + args.tile_size - 1) // args.tile_size)
        done = 0
        for row in range(0, template.height, args.tile_size):
            for col in range(0, template.width, args.tile_size):
                window = Window(col, row, min(args.tile_size, template.width-col),
                                min(args.tile_size, template.height-row))
                arrays = [sources[f].read(1, window=window, masked=True) for f in bundle["features"]]
                valid = np.logical_and.reduce([~np.ma.getmaskarray(a) & np.isfinite(a.filled(np.nan)) for a in arrays])
                matrix = np.column_stack([a.filled(np.nan).ravel() for a in arrays])
                flat_valid = valid.ravel()
                predictions = {key: np.full(matrix.shape[0], -9999.0, dtype="float32") for key in outputs}
                if flat_valid.any():
                    x = matrix[flat_valid]
                    predictions["probability"][flat_valid] = bundle["models"]["probability"].predict_proba(x)[:, 1]
                    predictions["frost_days"][flat_valid] = np.maximum(0, bundle["models"]["frost_days"].predict(x))
                    predictions["seasonal_tmin_c"][flat_valid] = bundle["models"]["seasonal_tmin_c"].predict(x)
                for key, dst in outputs.items():
                    dst.write(predictions[key].reshape(valid.shape), 1, window=window)
                done += 1
                if done % 25 == 0 or done == total:
                    print(f"LOCAL_RASTER_TILE_OK={done}/{total}", flush=True)
    print(f"LOCAL_RASTER_PREDICTION_OK={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
