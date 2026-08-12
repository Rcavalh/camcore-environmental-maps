from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import rasterio


MODULE = Path(__file__).resolve().parents[1]
DB = MODULE / "database"
CONFIG = MODULE / "config/source_roots.json"
MANIFEST = DB / "AVAILABLE_ENVIRONMENTAL_ASSET_MANIFEST.parquet"
OUT = MODULE / "outputs/full_native_input_audit"

REQUIRED = [
    ("modis-11A1-061", "LST_Night_1km", 2000),
    ("modis-09A1-061", "sur_refl_b02", 2000),
    ("modis-15A3H-061", "Lai_500m", 2002),
    ("modis-15A3H-061", "Fpar_500m", 2002),
    ("modis-17A2HGF-061", "Gpp_500m", 2000),
    ("modis-43A4-061", "Nadir_Reflectance_Band1", 2000),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    manifest = pd.read_parquet(MANIFEST, columns=[
        "state_group", "source_type", "collection", "asset", "acquisition_date", "stable",
    ])
    manifest = manifest.loc[manifest.stable.astype(bool)].copy()
    manifest["date"] = pd.to_datetime(manifest.acquisition_date, errors="coerce")
    manifest["year"] = manifest.date.dt.year
    rows = []
    for collection, asset, expected_first in REQUIRED:
        selected = manifest.loc[manifest.source_type.eq("MODIS") & manifest.collection.eq(collection) & manifest.asset.eq(asset)]
        for group in ["PR_SC", "RS", "SP", "MS"]:
            block = selected.loc[selected.state_group.eq(group)]
            first = int(block.year.min()) if block.year.notna().any() else None
            last = int(block.year.max()) if block.year.notna().any() else None
            rows.append({
                "state_group": group, "collection": collection, "representative_asset": asset,
                "files": len(block), "first_year": first, "last_year": last,
                "expected_first_year": expected_first,
                "historical_start_complete": bool(first is not None and first <= expected_first),
                "current_end_present": bool(last is not None and last >= 2025),
            })
    coverage = pd.DataFrame(rows)
    coverage.to_csv(OUT / "MODIS_REQUIRED_PRODUCT_TEMPORAL_COVERAGE.csv", index=False)
    era5 = manifest.loc[manifest.source_type.eq("ERA5_LAND")].groupby("state_group", as_index=False).agg(files=("asset", "size"))
    era5["expected_files"] = 1276
    era5["complete"] = era5.files.eq(era5.expected_files)
    era5.to_csv(OUT / "ERA5_REQUIRED_COVERAGE.csv", index=False)
    with rasterio.open(cfg["anadem_dem"]) as dem, rasterio.open(cfg["anadem_hand_2000m"]) as hand:
        terrain = {
            "dem_width": dem.width, "dem_height": dem.height, "bounding_grid_cells": dem.width * dem.height,
            "dem_valid_percent": float(dem.tags(1).get("STATISTICS_VALID_PERCENT", "nan")),
            "estimated_valid_cells": round(dem.width * dem.height * float(dem.tags(1).get("STATISTICS_VALID_PERCENT", 0)) / 100),
            "dem_hand_shape_aligned": dem.shape == hand.shape,
            "dem_hand_transform_aligned": all(abs(a-b) <= 1e-10 for a, b in zip(tuple(dem.transform), tuple(hand.transform))),
            "dem_resolution_degrees": list(dem.res), "dem_crs": str(dem.crs),
        }
    (OUT / "ANADEM_HAND_FULL_NATIVE_AUDIT.json").write_text(json.dumps(terrain, indent=2), encoding="utf-8")
    status = {
        "status": "FULL_NATIVE_INPUT_AUDIT_OK",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "era5_complete_all_state_groups": bool(era5.complete.all()),
        "modis_multisensor_complete_all_state_groups": bool((coverage.historical_start_complete & coverage.current_end_present).all()),
        "snapshot_smoke_ready": bool(era5.complete.all()),
        "full_multisensor_freeze_ready": bool(era5.complete.all() and (coverage.historical_start_complete & coverage.current_end_present).all()),
        "estimated_valid_anadem_cells": terrain["estimated_valid_cells"],
        "policy": "Smoke may use the current snapshot; the final multisensor native raster must wait for every required product gate.",
    }
    (OUT / "FULL_NATIVE_INPUT_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
