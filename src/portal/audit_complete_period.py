#!/usr/bin/env python3
"""Audit the four canonical complete-period GeoTIFFs without reading full rasters."""

from __future__ import annotations

import json
from pathlib import Path

import rasterio


ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "dryad_dataset" / "data" / "model_outputs" / "complete_period"
OUTPUT = ROOT / "dryad_dataset" / "metadata" / "COMPLETE_PERIOD_RASTER_AUDIT.json"
EXPECTED = (
    "FROST_PROBABILITY_MEAN_2000_2025.tif",
    "FROST_DAYS_MEAN_2000_2025.tif",
    "TMIN_MEAN_2000_2025.tif",
    "TMIN_P25_2000_2025.tif",
)


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    records = []
    missing = []
    for name in EXPECTED:
        path = DATA_DIR / name
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
            continue
        with rasterio.open(path) as src:
            records.append(
                {
                    "file": name,
                    "bytes": path.stat().st_size,
                    "driver": src.driver,
                    "width": src.width,
                    "height": src.height,
                    "count": src.count,
                    "dtype": src.dtypes[0],
                    "nodata": src.nodata,
                    "crs": src.crs.to_string() if src.crs else None,
                    "bounds": list(src.bounds),
                    "transform": list(src.transform)[:6],
                    "is_tiled": bool(src.is_tiled),
                    "block_shape": list(src.block_shapes[0]),
                    "compression": str(src.compression),
                    "overviews": src.overviews(1),
                    "statistics_tags": {
                        key: value
                        for key, value in src.tags(1).items()
                        if key.startswith("STATISTICS_")
                    },
                }
            )

    result = {
        "status": "COMPLETE_PERIOD_RASTER_AUDIT_OK" if not missing else "INCOMPLETE",
        "expected_count": len(EXPECTED),
        "verified_count": len(records),
        "missing": missing,
        "rasters": records,
    }
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{result['status']}={OUTPUT}")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
