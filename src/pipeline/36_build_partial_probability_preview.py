from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling
from rasterio.warp import reproject


MODULE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = MODULE / "outputs/hpc_full_native_balanced_rf_all_2000_2025"
RASTER_NAME = "RF_BALANCED_FROST_PROBABILITY_ALL_2000_2025_ANADEM30M.tif"
NODATA = np.float32(-9999.0)


def completed_rasters(root: Path) -> list[Path]:
    rasters: list[Path] = []
    for marker in sorted((root / "shards_512").glob("shard_*/SHARD_*_OK")):
        raster = marker.parent / "rasters" / RASTER_NAME
        if raster.is_file() and raster.stat().st_size > 0:
            rasters.append(raster)
    return rasters


def main(scale: float) -> int:
    root = Path(os.environ.get("FROST_OUTPUT", DEFAULT_OUTPUT)).resolve()
    sources = completed_rasters(root)
    if not sources:
        raise SystemExit(f"No completed shard rasters found under {root}")

    preview_dir = root / "partial_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output = preview_dir / "RF_FROST_PROBABILITY_PARTIAL_LIGHT.tif"

    with rasterio.open(sources[0]) as reference:
        width = max(1, int(round(reference.width * scale)))
        height = max(1, int(round(reference.height * scale)))
        transform = reference.transform * Affine.scale(
            reference.width / width, reference.height / height
        )
        destination = np.full((height, width), NODATA, dtype=np.float32)
        profile = reference.profile.copy()
        profile.update(
            driver="GTiff",
            width=width,
            height=height,
            transform=transform,
            dtype="float32",
            count=1,
            nodata=float(NODATA),
            compress="DEFLATE",
            predictor=3,
            tiled=True,
            blockxsize=256,
            blockysize=256,
            BIGTIFF="IF_SAFER",
        )

    for index, path in enumerate(sources, start=1):
        with rasterio.open(path) as source:
            reproject(
                source=rasterio.band(source, 1),
                destination=destination,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=transform,
                dst_crs=source.crs,
                dst_nodata=float(NODATA),
                resampling=Resampling.nearest,
                init_dest_nodata=index == 1,
                num_threads=4,
            )
        print(f"PARTIAL_PREVIEW_SOURCE_OK={index}/{len(sources)} {path.parent.parent.name}", flush=True)

    with rasterio.open(output, "w", **profile) as target:
        target.write(destination, 1)
        target.update_tags(
            status="PARTIAL_PREVIEW",
            completed_shards=len(sources),
            total_shards=96,
            scale_fraction=scale,
            warning="Contains completed shards only; blank regions are not predictions.",
        )
        factors = [factor for factor in (2, 4, 8, 16) if width // factor >= 1 and height // factor >= 1]
        if factors:
            target.build_overviews(factors, Resampling.nearest)
            target.update_tags(ns="rio_overview", resampling="nearest")

    valid = destination != NODATA
    print(f"PARTIAL_PREVIEW_OK={output}", flush=True)
    print(f"completed_shards={len(sources)} valid_preview_pixels={int(valid.sum())}", flush=True)
    if valid.any():
        print(
            f"minimum={float(destination[valid].min()):.6f} "
            f"maximum={float(destination[valid].max()):.6f}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", type=float, default=0.05)
    options = parser.parse_args()
    if not 0 < options.scale <= 1:
        parser.error("--scale must be in (0, 1]")
    raise SystemExit(main(options.scale))
