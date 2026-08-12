#!/usr/bin/env python
"""Create a deterministic raster catalog and SHA-256 manifest for the Dryad workspace."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import rasterio


DRYAD = Path(__file__).resolve().parents[3] / "dryad_dataset"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def status_for(path: Path) -> str:
    rel = path.relative_to(DRYAD).as_posix()
    if rel.startswith("source_data_pending_license_review/"):
        return "HOLD_LICENSE_REVIEW"
    if "development_only" in rel:
        return "EXCLUDE_DEVELOPMENT_PREVIEW"
    if "derived_terrain" in rel:
        return "REVIEW_DERIVED_DATA_LICENSE"
    return "READY_AFTER_FINAL_QC"


def main() -> int:
    rasters = sorted(DRYAD.rglob("*.tif")) + sorted(DRYAD.rglob("*.tiff"))
    rows = []
    checksums = []
    for path in rasters:
        with rasterio.open(path) as src:
            bounds = src.bounds
            rows.append({
                "file": path.relative_to(DRYAD).as_posix(),
                "status": status_for(path),
                "bytes": path.stat().st_size,
                "width": src.width,
                "height": src.height,
                "bands": src.count,
                "dtype": src.dtypes[0],
                "crs": src.crs.to_string() if src.crs else "",
                "resolution_x": src.res[0],
                "resolution_y": src.res[1],
                "left": bounds.left,
                "bottom": bounds.bottom,
                "right": bounds.right,
                "top": bounds.top,
                "nodata": src.nodata,
            })
        digest = sha256(path)
        checksums.append((digest, path.relative_to(DRYAD).as_posix()))
        print(f"CATALOG_RASTER_OK={path.name}")

    catalog = DRYAD / "metadata" / "RASTER_CATALOG.csv"
    with catalog.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    checksum_file = DRYAD / "metadata" / "SHA256SUMS.txt"
    checksum_file.write_text("".join(f"{digest}  {name}\n" for digest, name in checksums), encoding="utf-8")
    print(f"RASTER_CATALOG_OK={catalog}")
    print(f"SHA256_MANIFEST_OK={checksum_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
