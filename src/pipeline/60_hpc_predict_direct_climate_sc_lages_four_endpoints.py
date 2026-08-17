from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window


MODULE = Path(__file__).resolve().parents[1]
PROJECT = MODULE.parent.parent
RUNROOT = MODULE / "hpc_direct_climate_sc_lages_smoke"
INPUTS = RUNROOT / "inputs/climate_annual"
DEFAULT_OUTPUT = (
    MODULE
    / "outputs/article_v2_0_direct_grids"
    / "hpc_direct_climate_sc_lages_smoke_2000_2026"
)
DEFAULT_BOUNDS = (-50.40, -28.05, -48.35, -27.35)
NODATA = np.float32(-9999.0)
ARTICLE_VERSION = "2.0"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class ClimateStack:
    def __init__(self, path: Path, transform, crs, width: int, height: int, resampling):
        self.path = path
        self.source = rasterio.open(path)
        self.vrt = WarpedVRT(
            self.source,
            crs=crs,
            transform=transform,
            width=width,
            height=height,
            resampling=resampling,
            nodata=self.source.nodata,
        )
        self.names = list(self.source.descriptions)
        if any(not name for name in self.names):
            raise RuntimeError(f"Missing band descriptions: {path}")

    def read(self, window: Window) -> np.ndarray:
        return self.vrt.read(window=window, masked=True).astype(np.float32).filled(np.nan)

    def close(self):
        self.vrt.close()
        self.source.close()


def raster_profile(source, window: Window) -> dict:
    profile = source.profile.copy()
    profile.update(
        width=int(window.width),
        height=int(window.height),
        transform=source.window_transform(window),
        count=1,
        dtype="float32",
        nodata=float(NODATA),
        compress="DEFLATE",
        predictor=3,
        tiled=True,
        blockxsize=512,
        blockysize=512,
        BIGTIFF="IF_SAFER",
    )
    return profile


def output_contract(
    output: Path,
    label: str,
    period_label: str,
    enso_phases: list[str] | None = None,
    probability_only: bool = False,
) -> dict[str, Path]:
    rasters = output / "rasters"
    paths = {
        "probability": rasters / f"RF_DIRECT_GRIDS_FROST_PROBABILITY_MEAN_{period_label}_{label}_ANADEM30M.tif",
        "frost_days": rasters / f"RF_DIRECT_GRIDS_EXPECTED_FROST_DAYS_MEAN_{period_label}_{label}_ANADEM30M.tif",
        "seasonal_tmin_mean": rasters / f"RF_DIRECT_GRIDS_SEASONAL_MINIMUM_TEMPERATURE_C_MEAN_{period_label}_{label}_ANADEM30M.tif",
        "seasonal_tmin_p25": rasters / f"RF_DIRECT_GRIDS_SEASONAL_MINIMUM_TEMPERATURE_C_P25_{period_label}_{label}_ANADEM30M.tif",
    }
    if probability_only:
        return {"probability": paths["probability"]}
    for phase in enso_phases or []:
        paths[f"probability_enso_{phase.lower()}"] = (
            rasters / f"RF_DIRECT_GRIDS_FROST_PROBABILITY_MEAN_ENSO_{phase}_{label}_ANADEM30M.tif"
        )
        paths[f"seasonal_tmin_p25_enso_{phase.lower()}"] = (
            rasters / f"RF_DIRECT_GRIDS_SEASONAL_MINIMUM_TEMPERATURE_C_P25_ENSO_{phase}_{label}_ANADEM30M.tif"
        )
    return paths


def load_enso_contract(path: Path, years: list[int]) -> tuple[dict[int, str], dict[str, list[int]]]:
    table = pd.read_csv(path)
    required = {"year", "enso_phase"}
    if not required.issubset(table.columns):
        raise RuntimeError(f"ENSO table must contain {sorted(required)}: {path}")
    labels = {"El Nino": "EL_NINO", "La Nina": "LA_NINA", "Neutral": "NEUTRAL"}
    table = table.loc[table.year.astype(int).isin(years)].copy()
    duplicated = table.loc[table.year.astype(int).duplicated(), "year"].astype(int).tolist()
    if duplicated:
        raise RuntimeError(f"Duplicated ENSO years: {duplicated}")
    by_year = {
        int(row.year): labels[str(row.enso_phase).strip()]
        for row in table.itertuples(index=False)
        if str(row.enso_phase).strip() in labels
    }
    missing = [year for year in years if year not in by_year]
    if missing:
        raise RuntimeError(f"ENSO classification missing for years: {missing}")
    by_phase = {
        phase: [year for year in years if by_year[year] == phase]
        for phase in ["EL_NINO", "LA_NINA", "NEUTRAL"]
    }
    empty = [phase for phase, selected in by_phase.items() if not selected]
    if empty:
        raise RuntimeError(f"ENSO phases without years in requested period: {empty}")
    return by_year, by_phase


def render_figure(paths: dict[str, Path], output: Path, label: str, period_label: str):
    specs = [
        ("probability", "Frost probability", "RdYlBu", 0, 1),
        ("frost_days", "Expected frost days", "RdYlBu", None, None),
        ("seasonal_tmin_mean", "Seasonal minimum temperature â€” mean (Â°C)", "RdYlBu_r", None, None),
        ("seasonal_tmin_p25", "Seasonal minimum temperature â€” P25 (Â°C)", "RdYlBu_r", None, None),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5), constrained_layout=True)
    for letter, (ax, (key, title, cmap, fixed_min, fixed_max)) in enumerate(zip(axes.ravel(), specs)):
        with rasterio.open(paths[key]) as src:
            factor = max(1, int(max(src.width, src.height) / 1800))
            arr = src.read(
                1,
                out_shape=(max(1, src.height // factor), max(1, src.width // factor)),
                masked=True,
                resampling=Resampling.nearest,
            ).filled(np.nan)
            bounds = src.bounds
        valid = arr[np.isfinite(arr)]
        vmin = fixed_min if fixed_min is not None else float(np.percentile(valid, 1))
        vmax = fixed_max if fixed_max is not None else float(np.percentile(valid, 99))
        image = ax.imshow(
            arr,
            extent=(bounds.left, bounds.right, bounds.bottom, bounds.top),
            origin="upper",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            interpolation="nearest",
        )
        ax.set_title(f"({chr(97 + letter)}) {title}", fontsize=10)
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
    fig.suptitle(
        f"Direct ERA5-Land and MODIS climate grids â€” {label} ({period_label})",
        fontsize=13,
    )
    figure_dir = output / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    full = figure_dir / f"RF_DIRECT_GRIDS_{label}_FOUR_ENDPOINTS_{period_label}_620DPI.png"
    light = figure_dir / f"RF_DIRECT_GRIDS_{label}_FOUR_ENDPOINTS_{period_label}_LIGHT.png"
    fig.savefig(full, dpi=620, bbox_inches="tight", facecolor="white")
    fig.savefig(light, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main(args) -> int:
    started = time.time()
    output_root = Path(args.output_dir)
    output = (
        output_root
        if args.shard_count == 1
        else output_root
        / f"shards_{args.tile_size}"
        / f"shard_{args.shard_index:02d}_of_{args.shard_count:02d}"
    )
    inputs = Path(args.input_dir)
    label = args.label.strip().upper().replace(" ", "_")
    (output / "rasters").mkdir(parents=True, exist_ok=True)
    (output / "figures").mkdir(parents=True, exist_ok=True)
    checkpoints = output / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    config_path = Path(os.environ.get("FROST_CONFIG", RUNROOT / "config/source_roots_hpc.json"))
    model_path = Path(os.environ.get(
        "FROST_MODEL",
        MODULE / "outputs/reduced_rf_2026_provisional_production/models/RF_REDUCED_ALL_ENDPOINTS_2000_2026_PROVISIONAL.joblib",
    ))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    bundle = joblib.load(model_path)
    features = list(bundle["features"])
    imputer = bundle["imputer"]
    models = bundle["models"]
    for model in models.values():
        if hasattr(model, "n_jobs"):
            model.n_jobs = args.model_workers
    if len(features) != 115:
        raise RuntimeError(f"Expected the frozen 115-predictor bundle, found {len(features)}")

    core = load_module("direct_smoke_core", MODULE / "scripts/08_run_five_state_50000_smoke.py")
    engine = load_module("direct_smoke_terrain", PROJECT / "4.Modelling/scripts/58_build_rf_50km_fold_test.py")
    engine.TEST_RESOLUTION_M = 30.0
    dem_path = Path(config["anadem_dem"])
    # New runs may explicitly provide a 15-km HAND product. Legacy article
    # versions remain unchanged because they still expose only the 2-km key.
    hand_path = Path(
        config["anadem_hand_15000m"]
        if "anadem_hand_15000m" in config
        else config["anadem_hand_2000m"]
    )
    hand_flowpath_radius_m = int(config.get("hand_flowpath_radius_m", 2000))
    bounds = tuple(args.bounds)
    halo = int(math.ceil(2000 / 30.0)) + 5

    with rasterio.open(dem_path) as dem_src:
        core_window = rasterio.windows.from_bounds(*bounds, transform=dem_src.transform).round_offsets().round_lengths()
        col0 = max(int(core_window.col_off), 0)
        row0 = max(int(core_window.row_off), 0)
        core_window = Window(
            col0,
            row0,
            min(int(core_window.width), dem_src.width - col0),
            min(int(core_window.height), dem_src.height - row0),
        )
        profile = raster_profile(dem_src, core_window)
        crop_transform = profile["transform"]
        crop_crs = profile["crs"]

    height, width = int(core_window.height), int(core_window.width)
    valid_pixels = 0
    years = sorted(set(args.years)) if args.years else list(range(args.start_year, args.end_year + 1))
    period_label = args.period_label or (
        f"{years[0]}_{years[-1]}" if years == list(range(years[0], years[-1] + 1))
        else "YEARS_" + "_".join(map(str, years))
    )
    enso_by_year: dict[int, str] = {}
    enso_by_phase: dict[str, list[int]] = {}
    if args.enso_csv:
        enso_by_year, enso_by_phase = load_enso_contract(Path(args.enso_csv), years)
    print(
        f"DIRECT_SC_SMOKE_GRID_OK width={width} height={height} valid_pixels={valid_pixels} "
        f"years={len(years)}",
        flush=True,
    )

    input_labels = [value.strip().upper() for value in args.input_labels]
    stack_groups = {}
    for year in years:
        stack_groups[year] = []
        for input_label in input_labels:
            stack_groups[year].extend([
                ClimateStack(inputs / f"ERA5_CONTINUOUS_{year}_{input_label}.tif", crop_transform, crop_crs, width, height, Resampling.bilinear),
                ClimateStack(inputs / f"ERA5_DISCRETE_{year}_{input_label}.tif", crop_transform, crop_crs, width, height, Resampling.nearest),
                ClimateStack(inputs / f"MODIS_CONTINUOUS_{year}_{input_label}.tif", crop_transform, crop_crs, width, height, Resampling.bilinear),
                ClimateStack(inputs / f"MODIS_DISCRETE_{year}_{input_label}.tif", crop_transform, crop_crs, width, height, Resampling.nearest),
            ])

    paths = output_contract(
        output,
        label,
        period_label,
        list(enso_by_phase),
        probability_only=args.probability_only,
    )
    writers = {}
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        writers[key] = rasterio.open(path, "r+" if path.exists() else "w", **({} if path.exists() else profile))
        writers[key].update_tags(
            article_version=ARTICLE_VERSION,
            method="Random Forest with direct ERA5-Land and MODIS source grids",
            period=period_label,
            event_window="15 May to 15 August",
            post_prediction_smoothing="none",
            climate_alignment="bilinear continuous; nearest count variables",
            output_endpoint=key,
        )

    tile_total = math.ceil(height / args.tile_size) * math.ceil(width / args.tile_size)
    tile_index = 0
    try:
        with rasterio.open(dem_path) as dem_source, rasterio.open(hand_path) as hand_source:
            for tile_row in range(0, height, args.tile_size):
                for tile_col in range(0, width, args.tile_size):
                    tile_started = time.time()
                    tile_height = min(args.tile_size, height - tile_row)
                    tile_width = min(args.tile_size, width - tile_col)
                    window = Window(tile_col, tile_row, tile_width, tile_height)
                    full_window = Window(
                        int(core_window.col_off) + tile_col,
                        int(core_window.row_off) + tile_row,
                        tile_width,
                        tile_height,
                    )
                    exp_row0 = max(int(full_window.row_off) - halo, 0)
                    exp_col0 = max(int(full_window.col_off) - halo, 0)
                    exp_row1 = min(int(full_window.row_off + full_window.height) + halo, dem_source.height)
                    exp_col1 = min(int(full_window.col_off + full_window.width) + halo, dem_source.width)
                    expanded = Window(exp_col0, exp_row0, exp_col1 - exp_col0, exp_row1 - exp_row0)
                    dem = dem_source.read(1, window=expanded, masked=True).filled(np.nan).astype(np.float32)
                    hand = hand_source.read(1, window=expanded, masked=True).filled(np.nan).astype(np.float32)
                    hand = np.where(np.isfinite(hand) & (hand != 0), hand, np.nan).astype(np.float32)
                    local_row0 = int(full_window.row_off) - exp_row0
                    local_col0 = int(full_window.col_off) - exp_col0
                    local_row1 = local_row0 + tile_height
                    local_col1 = local_col0 + tile_width
                    tile_valid = np.isfinite(dem[local_row0:local_row1, local_col0:local_col1])
                    local_rows, local_cols = np.where(tile_valid)
                    n = len(local_rows)
                    valid_pixels += n
                    tile_index += 1
                    if (tile_index - 1) % args.shard_count != args.shard_index:
                        continue
                    marker = checkpoints / f"tile_r{tile_row:06d}_c{tile_col:06d}.json"
                    if marker.exists():
                        continue
                    if n == 0:
                        blank = np.full((tile_height, tile_width), NODATA, np.float32)
                        for writer in writers.values():
                            writer.write(blank, 1, window=window)
                        marker.write_text(json.dumps({"tile": tile_index, "total": tile_total, "valid": 0}), encoding="utf-8")
                        print(f"DIRECT_SC_SMOKE_TILE_OK={tile_index}/{tile_total} valid=0", flush=True)
                        continue

                    terrain_all = engine.terrain_stack(dem, hand)
                    terrain = {
                        name: terrain_all[name][local_row0:local_row1, local_col0:local_col1]
                        for name in core.TERRAIN_FEATURES
                    }

                    global_rows = local_rows + tile_row
                    global_cols = local_cols + tile_col
                    lon, lat = rasterio.transform.xy(crop_transform, global_rows, global_cols, offset="center")
                    lon = np.asarray(lon, np.float32)
                    lat = np.asarray(lat, np.float32)
                    constant = pd.DataFrame(index=np.arange(n), columns=features, dtype=np.float32)
                    constant["latitude"] = lat
                    constant["longitude"] = lon
                    for name in core.TERRAIN_FEATURES:
                        if name in constant:
                            constant[name] = terrain[name][local_rows, local_cols]

                    probability_sum = np.zeros(n, np.float64)
                    frost_days_sum = None if args.probability_only else np.zeros(n, np.float64)
                    tmin_sum = None if args.probability_only else np.zeros(n, np.float64)
                    tmin_years = None if args.probability_only else np.empty((len(years), n), np.float32)
                    phase_probability_sum = {
                        phase: np.zeros(n, np.float64) for phase in enso_by_phase
                    }
                    for year_index, year in enumerate(years):
                        frame = constant.copy()
                        frame["year"] = year
                        climate_samples = {}
                        for stack in stack_groups[year]:
                            values = stack.read(window)
                            sampled = values[:, local_rows, local_cols]
                            for band, name in enumerate(stack.names):
                                climate_samples.setdefault(name, []).append(sampled[band])
                        for name, parts in climate_samples.items():
                            if len(parts) == 1:
                                frame[name] = parts[0]
                            else:
                                climate_stack = np.stack(parts)
                                finite_count = np.isfinite(climate_stack).sum(axis=0)
                                frame[name] = np.divide(
                                    np.nansum(climate_stack, axis=0),
                                    finite_count,
                                    out=np.full(n, np.nan, np.float32),
                                    where=finite_count > 0,
                                )
                        x = imputer.transform(frame[features]).astype(np.float32)
                        probability = models["probability"].predict_proba(x)[:, 1]
                        probability_sum += probability
                        if not args.probability_only:
                            frost_days = np.clip(models["frost_days"].predict(x), 0, None)
                            tmin = models["seasonal_tmin_c"].predict(x)
                            frost_days_sum += frost_days
                            tmin_sum += tmin
                            tmin_years[year_index] = tmin
                        if enso_by_year:
                            phase_probability_sum[enso_by_year[year]] += probability

                    outputs = {
                        "probability": (probability_sum / len(years)).astype(np.float32),
                    }
                    if not args.probability_only:
                        outputs.update({
                            "frost_days": (frost_days_sum / len(years)).astype(np.float32),
                            "seasonal_tmin_mean": (tmin_sum / len(years)).astype(np.float32),
                            "seasonal_tmin_p25": np.percentile(tmin_years, 25, axis=0).astype(np.float32),
                        })
                        for phase, phase_years in enso_by_phase.items():
                            indices = [years.index(year) for year in phase_years]
                            outputs[f"probability_enso_{phase.lower()}"] = (
                                phase_probability_sum[phase] / len(phase_years)
                            ).astype(np.float32)
                            outputs[f"seasonal_tmin_p25_enso_{phase.lower()}"] = np.percentile(
                                tmin_years[indices], 25, axis=0
                            ).astype(np.float32)
                    for key, values in outputs.items():
                        tile = np.full((tile_height, tile_width), NODATA, np.float32)
                        tile[local_rows, local_cols] = values
                        writers[key].write(tile, 1, window=window)
                    marker.write_text(
                        json.dumps({"tile": tile_index, "total": tile_total, "valid": n}),
                        encoding="utf-8",
                    )
                    elapsed = time.time() - tile_started
                    print(
                        f"DIRECT_SC_SMOKE_TILE_OK={tile_index}/{tile_total} valid={n} seconds={elapsed:.3f}",
                        flush=True,
                    )
                    if args.max_tiles and len(list(checkpoints.glob("tile_*.json"))) >= args.max_tiles:
                        break
                if args.max_tiles and len(list(checkpoints.glob("tile_*.json"))) >= args.max_tiles:
                    break
    finally:
        for writer in writers.values():
            writer.close()
        for stacks in stack_groups.values():
            for stack in stacks:
                stack.close()

    partial_run = bool(args.max_tiles)
    if args.shard_count == 1 and not partial_run and not args.probability_only:
        render_figure(paths, output, label, period_label)
    summaries = {}
    for key, path in paths.items():
        if args.shard_count > 1 or partial_run:
            summaries[key] = {"path": str(path), "bytes": path.stat().st_size}
            continue
        with rasterio.open(path) as src:
            sample = src.read(
                1,
                out_shape=(max(1, src.height // 20), max(1, src.width // 20)),
                masked=True,
                resampling=Resampling.nearest,
            ).compressed()
            summaries[key] = {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sample_minimum": float(sample.min()),
                "sample_mean": float(sample.mean()),
                "sample_maximum": float(sample.max()),
            }
    status = {
        "status": "HPC_DIRECT_CLIMATE_SC_LAGES_SMOKE_OK",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "bounds": list(bounds),
        "label": label,
        "years": years,
        "period_label": period_label,
        "enso_csv": str(Path(args.enso_csv).resolve()) if args.enso_csv else None,
        "enso_years": enso_by_phase,
        "event_window": "15 May to 15 August",
        "grid": {"width": width, "height": height, "valid_pixels": valid_pixels},
        "predictors": len(features),
        "idw_used": False,
        "post_prediction_smoothing": False,
        "hand_source": str(hand_path),
        "hand_flowpath_radius_m": hand_flowpath_radius_m,
        "outputs": summaries,
        "elapsed_seconds": time.time() - started,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "partial_run": partial_run,
        "probability_only": args.probability_only,
        "completed_tiles": len(list(checkpoints.glob("tile_*.json"))),
    }
    (output / "STATUS.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    if not partial_run:
        marker_name = (
            "HPC_DIRECT_CLIMATE_SC_LAGES_SMOKE_OK"
            if args.shard_count == 1
            else f"SHARD_{args.shard_index:02d}_OF_{args.shard_count:02d}_OK"
        )
        (output / marker_name).write_text("OK\n", encoding="utf-8")
        print(marker_name, flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--years", type=int, nargs="+")
    parser.add_argument("--period-label")
    parser.add_argument("--enso-csv")
    parser.add_argument("--bounds", type=float, nargs=4, default=DEFAULT_BOUNDS)
    parser.add_argument("--label", default="SC_FLORI_LAGES")
    parser.add_argument("--input-dir", default=str(INPUTS))
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--model-workers", type=int, default=8)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--input-labels", nargs="+", default=["SC_FLORI_LAGES"])
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--max-tiles", type=int, default=0)
    parser.add_argument("--probability-only", action="store_true")
    parsed = parser.parse_args()
    if parsed.shard_count < 1 or not 0 <= parsed.shard_index < parsed.shard_count:
        parser.error("--shard-index must be in [0, --shard-count)")
    raise SystemExit(main(parsed))
