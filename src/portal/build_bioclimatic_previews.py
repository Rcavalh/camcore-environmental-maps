#!/usr/bin/env python3
"""Build web previews and numerical inspection grids for BIO1-BIO19."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling

DEFAULT_SOURCE = Path(r"Z:\ENVIROMICS\Camcore26\Articles\9.Data_paper_SSTool\rasters_BIO")
NODATA = 65535
QUANTIZED_MAXIMUM = 65534
MERCATOR_LIMIT = 85.05112878

VARIABLES = {
    1: ("Annual mean temperature", "Temperatura média anual", "°C", "temperature"),
    2: ("Mean diurnal range", "Amplitude térmica diurna média", "°C", "temperature"),
    3: ("Isothermality", "Isotermalidade", "%", "temperature"),
    4: ("Temperature seasonality", "Sazonalidade da temperatura", "SD × 100", "temperature"),
    5: ("Maximum temperature of warmest month", "Temperatura máxima do mês mais quente", "°C", "temperature"),
    6: ("Minimum temperature of coldest month", "Temperatura mínima do mês mais frio", "°C", "temperature"),
    7: ("Annual temperature range", "Amplitude térmica anual", "°C", "temperature"),
    8: ("Mean temperature of wettest quarter", "Temperatura média do trimestre mais úmido", "°C", "temperature"),
    9: ("Mean temperature of driest quarter", "Temperatura média do trimestre mais seco", "°C", "temperature"),
    10: ("Mean temperature of warmest quarter", "Temperatura média do trimestre mais quente", "°C", "temperature"),
    11: ("Mean temperature of coldest quarter", "Temperatura média do trimestre mais frio", "°C", "temperature"),
    12: ("Annual precipitation", "Precipitação anual", "mm", "precipitation"),
    13: ("Precipitation of wettest month", "Precipitação do mês mais úmido", "mm", "precipitation"),
    14: ("Precipitation of driest month", "Precipitação do mês mais seco", "mm", "precipitation"),
    15: ("Precipitation seasonality", "Sazonalidade da precipitação", "CV (%)", "precipitation"),
    16: ("Precipitation of wettest quarter", "Precipitação do trimestre mais úmido", "mm", "precipitation"),
    17: ("Precipitation of driest quarter", "Precipitação do trimestre mais seco", "mm", "precipitation"),
    18: ("Precipitation of warmest quarter", "Precipitação do trimestre mais quente", "mm", "precipitation"),
    19: ("Precipitation of coldest quarter", "Precipitação do trimestre mais frio", "mm", "precipitation"),
}
NEGATIVE_SENTINEL_LAYERS = {12, 13, 14, 16, 17, 18, 19}


def mercator_y(latitude: float | np.ndarray) -> float | np.ndarray:
    radians = np.radians(np.clip(latitude, -MERCATOR_LIMIT, MERCATOR_LIMIT))
    return np.log(np.tan(np.pi / 4.0 + radians / 2.0))


def web_mercator_preview(
    src: rasterio.io.DatasetReader,
    width: int,
    bio_number: int,
) -> tuple[np.ndarray, list[list[float]]]:
    west, source_south, east, source_north = map(float, src.bounds)
    south, north = max(source_south, -MERCATOR_LIMIT), min(source_north, MERCATOR_LIMIT)
    native_height = max(2, round(width * src.height / src.width))
    native = src.read(1, out_shape=(native_height, width), resampling=Resampling.nearest, masked=True)
    native_values = native.filled(np.nan).astype(np.float32)
    if bio_number in NEGATIVE_SENTINEL_LAYERS:
        native_values[native_values < 0] = np.nan

    top_y, bottom_y = float(mercator_y(north)), float(mercator_y(south))
    horizontal_span = np.radians(east - west)
    height = max(2, round(width * (top_y - bottom_y) / horizontal_span))
    destination_y = np.linspace(top_y, bottom_y, height, endpoint=False) - (top_y - bottom_y) / (2.0 * height)
    destination_latitude = np.degrees(2.0 * np.arctan(np.exp(destination_y)) - np.pi / 2.0)
    source_row = np.clip(
        (source_north - destination_latitude) / (source_north - source_south) * native_height - 0.5,
        0.0,
        native_height - 1.0,
    )
    nearest_row = np.rint(source_row).astype(np.int32)
    values = native_values[nearest_row].astype(np.float32)
    valid_rows = np.flatnonzero(np.isfinite(values).any(axis=1))
    if not valid_rows.size:
        return values, [[south, west], [north, east]]
    first_row, last_row = int(valid_rows[0]), int(valid_rows[-1])
    vertical_span = top_y - bottom_y
    cropped_north_y = top_y - first_row / height * vertical_span
    cropped_south_y = top_y - (last_row + 1) / height * vertical_span

    def latitude_from_y(value: float) -> float:
        return float(np.degrees(2.0 * np.arctan(np.exp(value)) - np.pi / 2.0))

    cropped_bounds = [[latitude_from_y(cropped_south_y), west], [latitude_from_y(cropped_north_y), east]]
    return values[first_row : last_row + 1], cropped_bounds


def colorize(values: np.ndarray, valid: np.ndarray, display_minimum: float, display_maximum: float) -> Image.Image:
    # Viridis-derived ramp requested for the portal: lower/worse = yellow, higher/better = blue.
    stops = np.array(
        [[253, 231, 37], [122, 209, 81], [34, 168, 132], [42, 120, 142], [54, 92, 141], [42, 50, 120]],
        dtype=np.float32,
    )
    span = max(display_maximum - display_minimum, np.finfo(np.float32).eps)
    normalized = np.clip((values - display_minimum) / span, 0.0, 1.0)
    scaled = normalized * (len(stops) - 1)
    lower = np.floor(scaled).astype(np.int16)
    upper = np.minimum(lower + 1, len(stops) - 1)
    fraction = (scaled - lower)[..., None]
    rgb = stops[lower] * (1.0 - fraction) + stops[upper] * fraction
    alpha = np.where(valid, 232, 0).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb.astype(np.uint8), alpha]), mode="RGBA")


def write_analysis_grid(
    output: Path,
    grid_id: str,
    values: np.ndarray,
    bounds: list[list[float]],
    minimum: float,
    maximum: float,
    units: str,
) -> None:
    valid = np.isfinite(values)
    encoded = np.full(values.shape, NODATA, dtype="<u2")
    span = max(maximum - minimum, np.finfo(np.float32).eps)
    encoded[valid] = np.rint(np.clip((values[valid] - minimum) / span, 0, 1) * QUANTIZED_MAXIMUM).astype("<u2")
    payload = {
        "id": grid_id,
        "width": int(values.shape[1]),
        "height": int(values.shape[0]),
        "bounds": bounds,
        "projection": "EPSG:3857",
        "minimum": minimum,
        "maximum": maximum,
        "nodata": NODATA,
        "quantizedMaximum": QUANTIZED_MAXIMUM,
        "units": units,
        "data": base64.b64encode(encoded.tobytes(order="C")).decode("ascii"),
    }
    output.write_text(
        "window.BIOCLIMATE_ANALYSIS_GRIDS = window.BIOCLIMATE_ANALYSIS_GRIDS || {};\n"
        f"window.BIOCLIMATE_ANALYSIS_GRIDS[{json.dumps(grid_id)}] = {json.dumps(payload, separators=(',', ':'))};\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--width", type=int, default=8640, help="Rendered global preview width.")
    parser.add_argument("--analysis-width", type=int, default=960)
    parser.add_argument("--webp-quality", type=int, default=90)
    args = parser.parse_args()

    preview_dir = args.web / "assets" / "bioclimate"
    analysis_dir = args.web / "assets" / "bioclimate-analysis"
    preview_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    for pattern, directory in (("*.webp", preview_dir), ("*.generated.js", analysis_dir)):
        for old in directory.glob(pattern):
            old.unlink()

    groups: dict[str, list[str]] = {"temperature": [], "precipitation": []}
    variable_layers: dict[str, list[dict[str, object]]] = {}
    analysis_manifest: dict[str, dict[str, object]] = {}
    for bio_number, (title, title_pt, units, group) in VARIABLES.items():
        source_path = args.source / f"BIO{bio_number}.tif"
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        print(f"BIOCLIMATE_BUILD_START={bio_number}/19 {source_path.name}", flush=True)
        with rasterio.open(source_path) as src:
            values, leaflet_bounds = web_mercator_preview(src, min(args.width, src.width), bio_number)
            valid = np.isfinite(values)
            if not valid.any():
                raise RuntimeError(f"No valid values in {source_path}")
            sampled = values[valid]
            minimum, maximum = float(sampled.min()), float(sampled.max())
            display_minimum, display_maximum = map(float, np.percentile(sampled, [2, 98]))
            preview = colorize(np.nan_to_num(values, nan=display_minimum), valid, display_minimum, display_maximum)
            output_name = f"BIO{bio_number:02d}.webp"
            preview.save(preview_dir / output_name, format="WEBP", quality=args.webp_quality, method=6, exact=True)

            analysis_values, _ = web_mercator_preview(src, min(args.analysis_width, src.width), bio_number)
            grid_id = f"bio{bio_number:02d}"
            grid_name = f"BIO{bio_number:02d}.generated.js"
            write_analysis_grid(
                analysis_dir / grid_name,
                grid_id,
                analysis_values,
                leaflet_bounds,
                minimum,
                maximum,
                units,
            )

        layer = {
            "id": grid_id,
            "gridId": grid_id,
            "code": f"BIO{bio_number}",
            "title": title,
            "titlePt": title_pt,
            "units": units,
            "image": f"assets/bioclimate/{output_name}?v=20260812bio1",
            "download": None,
            "bounds": leaflet_bounds,
            "minimum": round(minimum, 5),
            "maximum": round(maximum, 5),
            "mean": round(float(sampled.mean()), 5),
            "displayMinimum": round(display_minimum, 5),
            "displayMaximum": round(display_maximum, 5),
            "previewWidth": int(values.shape[1]),
            "previewHeight": int(values.shape[0]),
        }
        variable_key = f"BIO{bio_number} — {title}"
        groups[group].append(variable_key)
        variable_layers[variable_key] = [layer]
        analysis_manifest[grid_id] = {"url": f"assets/bioclimate-analysis/{grid_name}"}

    payload = {
        "period": "1981–2025",
        "resolution": "2.5 arc-minutes",
        "domain": "50°S–50°N; global longitudes",
        "groups": groups,
        "speciesLayers": variable_layers,
        "bioclimateLayers": variable_layers,
        "previewSpecies": list(variable_layers),
        "previewBioclimate": list(variable_layers),
        "analysisManifest": analysis_manifest,
        "palette": "Viridis-derived yellow-to-blue",
        "displayStretch": "2nd–98th percentile",
    }
    (args.web / "bioclimate.generated.js").write_text(
        "window.BIOCLIMATIC_VARIABLES = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    total = sum(len(items) for items in groups.values())
    print(f"BIOCLIMATE_PORTAL_OK={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
