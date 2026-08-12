from __future__ import annotations

import argparse
import calendar
from datetime import datetime, timezone
import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from pyproj import Transformer
import rasterio
from rasterio.transform import rowcol

warnings.filterwarnings("ignore", category=RuntimeWarning, message="Mean of empty slice")
warnings.filterwarnings("ignore", category=RuntimeWarning, message="Degrees of freedom")
warnings.filterwarnings("ignore", category=RuntimeWarning, message="All-NaN slice encountered")


MODULE = Path(__file__).resolve().parents[1]
CONFIG = MODULE / "config" / "source_roots.json"
DATABASE = MODULE / "database"
PARTITIONS = DATABASE / "era5_station_year_may15_aug15"
CHECKPOINT = MODULE / "checkpoints" / "era5_station_year"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-state-years", type=int, default=0)
    return parser.parse_args()


def resolve(project: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project / path


def variable_unit(variable: str) -> str:
    name = variable.lower()
    if "temperature" in name or "dewpoint" in name:
        return "degC"
    if "pressure" in name:
        return "Pa"
    if "wind" in name:
        return "m_s-1"
    if any(token in name for token in ("precipitation", "evaporation", "runoff")):
        return "source_daily_sum"
    if "radiation" in name or "heat_flux" in name:
        return "J_m-2_day-1"
    return "source_unit"


def convert(values: np.ndarray, variable: str) -> np.ndarray:
    result = values.astype(np.float32, copy=False)
    if "temperature" in variable.lower() or "dewpoint" in variable.lower():
        result = result - np.float32(273.15)
    return result


def selected_day_indices(year: int, month: int, observed_days: int):
    maximum = min(observed_days, calendar.monthrange(year, month)[1])
    days = np.arange(1, maximum + 1)
    keep = np.ones(maximum, dtype=bool)
    if month == 5:
        keep &= days >= 15
    if month == 8:
        keep &= days <= 15
    return np.where(keep)[0]


def fingerprint(paths):
    return {str(path): path.stat().st_size for path in sorted(paths)}


def station_indexes(src, stations):
    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    xx, yy = transformer.transform(stations.longitude.to_numpy(), stations.latitude.to_numpy())
    rows, cols = rowcol(src.transform, xx, yy)
    rows, cols = np.asarray(rows), np.asarray(cols)
    valid = (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width)
    return rows, cols, valid


def summarize(stations, variable, arrays, state_group, year, source_files, expected_files):
    values = np.concatenate(arrays, axis=0) if arrays else np.empty((0, len(stations)))
    valid = np.isfinite(values)
    count = valid.sum(axis=0)
    with np.errstate(all="ignore"):
        rows = pd.DataFrame({
            "state_group": state_group,
            "state": stations.state.to_numpy(),
            "station_id": stations.station_id.to_numpy(),
            "source": stations.source.to_numpy(),
            "latitude": stations.latitude.to_numpy(),
            "longitude": stations.longitude.to_numpy(),
            "year": year,
            "window_id": "may15_aug15",
            "source_variable": variable,
            "unit": variable_unit(variable),
            "n_valid_days": count,
            "mean": np.nanmean(values, axis=0) if len(values) else np.nan,
            "sd": np.nanstd(values, axis=0) if len(values) else np.nan,
            "minimum": np.nanmin(values, axis=0) if len(values) else np.nan,
            "p05": np.nanpercentile(values, 5, axis=0) if len(values) else np.nan,
            "p25": np.nanpercentile(values, 25, axis=0) if len(values) else np.nan,
            "p50": np.nanpercentile(values, 50, axis=0) if len(values) else np.nan,
            "p75": np.nanpercentile(values, 75, axis=0) if len(values) else np.nan,
            "p95": np.nanpercentile(values, 95, axis=0) if len(values) else np.nan,
            "maximum": np.nanmax(values, axis=0) if len(values) else np.nan,
            "source_files_available": source_files,
            "source_files_expected": expected_files,
        })
    if variable == "temperature_2m_min" and len(values):
        for threshold in (0, 2, 5):
            rows[f"days_le_{threshold}c"] = ((values <= threshold) & valid).sum(axis=0)
            rows[f"any_days_le_{threshold}c"] = (rows[f"days_le_{threshold}c"] > 0).astype("int8")
    else:
        for threshold in (0, 2, 5):
            rows[f"days_le_{threshold}c"] = np.nan
            rows[f"any_days_le_{threshold}c"] = np.nan
    return rows


def process_state_year(group, spec, root, stations, year):
    manifest = json.loads((root / "download_manifest.json").read_text(encoding="utf-8"))
    bands = list(manifest["bands"])
    variables_per_group = int(manifest.get("variables_per_group", 30))
    n_groups = int(manifest["n_variable_groups"])
    end_available = pd.Timestamp(manifest["end"])
    months = [m for m in range(5, 9) if pd.Timestamp(year=year, month=m, day=1) <= end_available]
    paths = [
        root / str(year) / f"era5land_daily_{year}_{month:02d}_group{group_no:02d}.tif"
        for month in months for group_no in range(1, n_groups + 1)
    ]
    available = [path for path in paths if path.is_file() and path.stat().st_size >= 10_000]
    if not available:
        return None
    current_fingerprint = fingerprint(available)
    marker = CHECKPOINT / f"{group}_{year}.json"
    output = PARTITIONS / f"state_group={group}" / f"year={year}" / "features.parquet"
    if marker.exists() and output.exists():
        previous = json.loads(marker.read_text(encoding="utf-8"))
        if previous.get("source_fingerprint") == current_fingerprint:
            print(f"ERA5_SKIP state={group} year={year} unchanged", flush=True)
            return previous

    arrays = {variable: [] for variable in bands}
    first = available[0]
    with rasterio.open(first) as src:
        rr, cc, inside = station_indexes(src, stations)
    if not inside.all():
        stations = stations.loc[inside].reset_index(drop=True)
        rr, cc = rr[inside], cc[inside]
    linear = None
    for group_no in range(1, n_groups + 1):
        offset = (group_no - 1) * variables_per_group
        group_vars = bands[offset: offset + variables_per_group]
        nvars = len(group_vars)
        for month in months:
            path = root / str(year) / f"era5land_daily_{year}_{month:02d}_group{group_no:02d}.tif"
            if path not in available:
                continue
            with rasterio.open(path) as src:
                observed_days = src.count // nvars
                if observed_days == 0:
                    continue
                data = src.read(masked=True).filled(np.nan).astype(np.float32)
                if linear is None or np.max(linear) >= src.width * src.height:
                    linear = rr * src.width + cc
                sampled = data.reshape(observed_days, nvars, src.height * src.width)[:, :, linear]
                day_index = selected_day_indices(year, month, observed_days)
                sampled = sampled[day_index]
                for local, variable in enumerate(group_vars):
                    arrays[variable].append(convert(sampled[:, local, :], variable))
            print(f"ERA5_READ state={group} year={year} month={month:02d} group={group_no:02d}", flush=True)
    frames = [
        summarize(stations, variable, variable_arrays, group, year, len(available), len(paths))
        for variable, variable_arrays in arrays.items() if variable_arrays
    ]
    if not frames:
        return None
    result = pd.concat(frames, ignore_index=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output, index=False)
    status = "COMPLETE" if len(available) == len(paths) else "PARTIAL"
    record = {
        "state_group": group, "state_codes": spec["state_codes"], "year": year,
        "status": status, "stations": int(result.station_id.nunique()),
        "variables": int(result.source_variable.nunique()), "rows": int(len(result)),
        "source_files_available": len(available), "source_files_expected": len(paths),
        "source_fingerprint": current_fingerprint, "output": str(output),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"ERA5_PARTITION_OK state={group} year={year} status={status} rows={len(result)}", flush=True)
    return record


def main():
    args = parse_args()
    PARTITIONS.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    project = Path(cfg["project_root"])
    station_path = resolve(project, cfg["station_catalog"])
    all_stations = pd.read_csv(station_path).drop_duplicates(["source", "station_id"])
    years = [2021] + list(range(2026, 2021, -1)) + list(range(2020, 1999, -1))
    processed = 0
    records = []
    for group, spec in cfg["states"].items():
        root = resolve(project, spec["era5"])
        stations = all_stations[all_stations.state.isin(spec["state_codes"])].reset_index(drop=True)
        if not (root / "download_manifest.json").exists() or stations.empty:
            continue
        for year in years:
            record = process_state_year(group, spec, root, stations, year)
            if record:
                records.append(record)
                processed += 1
                if args.max_state_years and processed >= args.max_state_years:
                    break
        if args.max_state_years and processed >= args.max_state_years:
            break
    all_markers = []
    for path in CHECKPOINT.glob("*.json"):
        try:
            all_markers.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    index = pd.DataFrame(all_markers)
    if not index.empty:
        index.drop(columns=["source_fingerprint"], errors="ignore").to_csv(
            DATABASE / "ERA5_STATION_YEAR_PARTITION_INDEX.csv", index=False
        )
    status = {
        "status": "FIVE_STATE_ERA5_INCREMENTAL_OK", "partitions": len(all_markers),
        "complete": sum(x.get("status") == "COMPLETE" for x in all_markers),
        "partial": sum(x.get("status") == "PARTIAL" for x in all_markers),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (DATABASE / "FIVE_STATE_ERA5_INTEGRATION_STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
