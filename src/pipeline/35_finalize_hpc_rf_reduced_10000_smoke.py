from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer


MODULE = Path(__file__).resolve().parents[1]
SOURCE = MODULE / "outputs/updated_historical_10000_smoke/tables/UPDATED_HISTORICAL_RF_10000_PREDICTIONS.parquet"
OUT = Path(os.environ.get("FROST_SMOKE_OUTPUT", MODULE / "outputs/hpc_rf_reduced_10000_smoke"))
RASTERS = {
    "probability": OUT / "RF_REDUCED_FROST_PROBABILITY_ALL_2000_2025_10000_SAMPLE.tif",
    "frost_days": OUT / "RF_REDUCED_EXPECTED_FROST_DAYS_ALL_2000_2025_10000_SAMPLE.tif",
    "seasonal_tmin_c": OUT / "RF_REDUCED_SEASONAL_MINIMUM_TEMPERATURE_C_ALL_2000_2025_10000_SAMPLE.tif",
}


def load_script(name: str, filename: str):
    path = MODULE / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def extract_values(points: pd.DataFrame, raster_path: Path) -> np.ndarray:
    if not raster_path.is_file() or raster_path.stat().st_size == 0:
        raise FileNotFoundError(raster_path)
    with rasterio.open(raster_path) as src:
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        x, y = transformer.transform(points.longitude.to_numpy(), points.latitude.to_numpy())
        values = np.fromiter(
            (sample[0] for sample in src.sample(zip(x, y), indexes=1)),
            dtype=np.float32,
            count=len(points),
        )
        if src.nodata is not None:
            values[values == src.nodata] = np.nan
    if np.isfinite(values).sum() < 9_900:
        raise RuntimeError(
            f"Too few values recovered from {raster_path.name}: "
            f"{np.isfinite(values).sum()}/{len(values)}"
        )
    return values


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    smoke = load_script("rf_reduced_smoke_plotter", "34_hpc_rf_reduced_10000_smoke.py")
    core = load_script("rf_reduced_smoke_core", "08_run_five_state_50000_smoke.py")
    points = pd.read_parquet(SOURCE)
    counts = points.groupby("state").size().to_dict()
    if len(points) != 10_000 or set(counts.values()) != {2_000}:
        raise RuntimeError(f"Unexpected smoke support: {counts}")
    for endpoint, path in RASTERS.items():
        points[endpoint] = extract_values(points, path)

    points.to_parquet(OUT / "RF_REDUCED_THREE_ENDPOINTS_10000.parquet", index=False)
    summary = pd.DataFrame([
        {"endpoint": endpoint, "n": int(points[endpoint].notna().sum()),
         "minimum": float(points[endpoint].min()), "mean": float(points[endpoint].mean()),
         "maximum": float(points[endpoint].max()), "output": str(path)}
        for endpoint, path in RASTERS.items()
    ])
    summary.to_csv(OUT / "RF_REDUCED_THREE_ENDPOINTS_10000_SUMMARY.csv", index=False)

    frost_vmax = float(points.frost_days.quantile(0.99))
    tmin_lo, tmin_hi = map(float, points.seasonal_tmin_c.quantile([0.01, 0.99]))
    smoke.plot_maps(points, core.load_boundaries(), [
        ("probability", "Frost-occurrence probability", "RdYlBu", 0.0, 1.0),
        ("frost_days", "Expected frost days per season", "RdYlBu", 0.0, frost_vmax),
        ("seasonal_tmin_c", "Seasonal minimum temperature (°C)", "RdYlBu_r", tmin_lo, tmin_hi),
    ])
    status = {
        "status": "HPC_RF_REDUCED_10000_SMOKE_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "recovered_from_existing_rasters": True,
        "points": len(points), "points_per_state": counts,
        "endpoints": list(RASTERS), "outputs": {key: str(value) for key, value in RASTERS.items()},
    }
    (OUT / "RUN_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    (OUT / "HPC_RF_REDUCED_10000_SMOKE_OK").write_text("OK\n", encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
