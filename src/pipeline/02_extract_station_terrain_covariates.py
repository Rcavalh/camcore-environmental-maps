from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from rasterio.transform import rowcol
from rasterio.windows import Window


MODULE = Path(__file__).resolve().parents[1]
CONFIG = MODULE / "config" / "source_roots.json"
DATABASE = MODULE / "database"
CHECKPOINT = MODULE / "checkpoints" / "terrain"
OUTPUT = DATABASE / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.parquet"
CSV_OUTPUT = DATABASE / "STATION_PHYSIOGRAPHIC_COVARIATES_ANADEM_30M.csv"
DERIVED = [
    "elevation", "slope_deg", "eastness", "northness", "TPI_native",
    "TRI_native", "roughness_native", "plan_curvature",
    "profile_curvature", "surface_curvature_laplacian",
    "cold_air_pooling_2000m", "elevation_above_local_min_2000m",
    "elevation_below_local_max_2000m", "local_relief_2000m",
    "local_sd_2000m",
]


def load_engine(project: Path):
    path = project / "4.Modelling/scripts/58_build_rf_50km_fold_test.py"
    spec = importlib.util.spec_from_file_location("five_state_terrain_engine", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load terrain engine: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    module.TEST_RESOLUTION_M = 30.0
    return module


def main():
    DATABASE.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    project = Path(cfg["project_root"])
    dem_path = Path(cfg["anadem_dem"])
    hand_path = Path(cfg["anadem_hand_2000m"])
    catalog_path = project / cfg["station_catalog"]
    stations = pd.read_csv(catalog_path)
    stations = stations.drop_duplicates(["source", "station_id"]).reset_index(drop=True)
    engine = load_engine(project)
    records = []
    with rasterio.open(dem_path) as src, rasterio.open(hand_path) as hand_src:
        if src.shape != hand_src.shape:
            raise RuntimeError(f"DEM/HAND shape mismatch: {src.shape} != {hand_src.shape}")
        if not src.transform.almost_equals(hand_src.transform, precision=1e-8):
            raise RuntimeError("DEM/HAND transforms are not aligned")
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        xx, yy = transformer.transform(stations.longitude.to_numpy(), stations.latitude.to_numpy())
        rows, cols = rowcol(src.transform, xx, yy)
        radius = int(math.ceil(2000 / 30.0)) + 5
        for number, (station, row, col) in enumerate(zip(stations.itertuples(index=False), rows, cols), 1):
            record = {
                "state": station.state, "source": station.source,
                "station_id": station.station_id, "latitude": float(station.latitude),
                "longitude": float(station.longitude), "anadem_source": str(dem_path),
                "hand_source": str(hand_path),
                "anadem_nominal_resolution_m": 30.0, "HAND_selected_m": np.nan,
                "HAND_status": "pending_extraction",
            }
            if row < 0 or col < 0 or row >= src.height or col >= src.width:
                record.update({name: np.nan for name in DERIVED})
                record["terrain_status"] = "outside_anadem"
                records.append(record)
                continue
            row0, col0 = max(row - radius, 0), max(col - radius, 0)
            row1, col1 = min(row + radius + 1, src.height), min(col + radius + 1, src.width)
            window = Window(col0, row0, col1 - col0, row1 - row0)
            dem = src.read(1, window=window, masked=True).filled(np.nan).astype(np.float32)
            hand_raw = hand_src.read(1, window=window, masked=True).filled(np.nan).astype(np.float32)
            # In this supplied product, source zeros were used to fill NA.
            hand = np.where(np.isfinite(hand_raw) & (hand_raw != 0), hand_raw, np.nan).astype(np.float32)
            local_row, local_col = row - row0, col - col0
            if not np.isfinite(dem[local_row, local_col]):
                record.update({name: np.nan for name in DERIVED})
                record["terrain_status"] = "anadem_nodata"
            else:
                terrain = engine.terrain_stack(dem, hand)
                record.update({name: float(terrain[name][local_row, local_col]) for name in DERIVED})
                record["HAND_selected_m"] = float(hand[local_row, local_col]) if np.isfinite(hand[local_row, local_col]) else np.nan
                record["HAND_status"] = "complete" if np.isfinite(record["HAND_selected_m"]) else "source_zero_filled_na"
                record["terrain_status"] = "complete_dem_derived"
            records.append(record)
            if number % 25 == 0 or number == len(stations):
                print(f"TERRAIN_STATIONS={number}/{len(stations)}", flush=True)
    result = pd.DataFrame(records)
    result.to_parquet(OUTPUT, index=False)
    result.to_csv(CSV_OUTPUT, index=False)
    registry = pd.DataFrame([
        {"feature": name, "block": "ANADEM-derived physiography", "scale": "native" if "2000m" not in name else "2000 m context", "available": True}
        for name in DERIVED
    ] + [{"feature": "HAND_selected_m", "block": "HAND", "scale": "2,000 m flow-path threshold; source zeros masked as NA", "available": True}])
    registry.to_csv(DATABASE / "PHYSIOGRAPHIC_COVARIATE_REGISTRY.csv", index=False)
    status = {
        "status": "FIVE_STATE_STATION_TERRAIN_OK",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stations": int(len(result)),
        "complete_dem_derived": int(result.terrain_status.eq("complete_dem_derived").sum()),
        "outside_or_nodata": int((~result.terrain_status.eq("complete_dem_derived")).sum()),
        "terrain_features": len(DERIVED),
        "hand_available": True,
        "hand_complete": int(result.HAND_status.eq("complete").sum()),
        "hand_zero_filled_na": int(result.HAND_status.eq("source_zero_filled_na").sum()),
        "hand_source": str(hand_path),
        "output": str(OUTPUT),
    }
    (DATABASE / "FIVE_STATE_STATION_TERRAIN_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (MODULE / "STATION_TERRAIN_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
