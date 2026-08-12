#!/usr/bin/env python3
"""Build native-resolution species previews and browser analysis grids."""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling

DEFAULT_SOURCE = Path(r"Z:\ENVIROMICS\Camcore26\Articles\9.Data_paper_SSTool")
NODATA = 65535
QUANTIZED_MAXIMUM = 65534
PREVIEW_SPECIES = {
    "Eucalyptus amplifolia": "Eucalyptus_amplifolia_parquet",
    "Eucalyptus urophylla": "Eucalyptus_urophylla_parquet",
}
LAYER_NAMES = {
    "overall": ("OVERALL_SUITABILITY", "Overall suitability", "Adequabilidade geral"),
    "scaled_koppen": ("KOPPEN_CLIMATE_OVERLAP", "K\u00f6ppen climate overlap", "Sobreposi\u00e7\u00e3o clim\u00e1tica de K\u00f6ppen"),
    "scaled_maha": ("PCA_MAHALANOBIS_SIMILARITY", "PCA\u2013Mahalanobis similarity", "Similaridade PCA\u2013Mahalanobis"),
    "scaled_total": ("BIOCLIMATIC_ENVELOPE", "Bioclimatic envelope", "Envelope bioclim\u00e1tico"),
}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def file_code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def display_name(folder_name: str) -> str:
    return folder_name.removesuffix("_parquet").replace("_", " ")


def colorize(values: np.ndarray, valid: np.ndarray) -> Image.Image:
    stops = np.array(
        [[255, 255, 204], [217, 240, 163], [173, 221, 142], [78, 179, 105], [0, 109, 44], [0, 56, 20]],
        dtype=np.float32,
    )
    scaled = np.clip(values, 0.0, 1.0) * (len(stops) - 1)
    lower = np.floor(scaled).astype(np.int16)
    upper = np.minimum(lower + 1, len(stops) - 1)
    fraction = (scaled - lower)[..., None]
    rgb = stops[lower] * (1.0 - fraction) + stops[upper] * fraction
    alpha = np.where(valid, 226, 0).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb.astype(np.uint8), alpha]), mode="RGBA")


def species_catalog(source: Path) -> dict[str, list[str]]:
    eucalypts = [
        display_name(path.name)
        for path in sorted((source / "species_rasters_all").iterdir())
        if path.is_dir() and path.name.startswith(("Eucalyptus_", "Corymbia_"))
    ]
    excluded = {"Pinus_tecunumanii_High_parquet", "Pinus_tecunumanii_Low_parquet"}
    pines = [
        display_name(path.name)
        for path in sorted((source / "species_rasters_pinus").iterdir())
        if path.is_dir() and path.name.startswith("Pinus_") and path.name not in excluded
    ]
    return {"eucalypts": eucalypts, "pines": pines}


def web_mercator_preview(src: rasterio.io.DatasetReader, width: int) -> tuple[np.ndarray, list[list[float]]]:
    west, south, east, north = map(float, src.bounds)
    if not src.crs or not src.crs.is_geographic:
        raise ValueError(f"Expected a geographic source raster, found {src.crs}")
    native_height = max(2, round(width * src.height / src.width))
    native = src.read(1, out_shape=(native_height, width), resampling=Resampling.nearest, masked=True)
    native_values = native.filled(np.nan).astype(np.float32)

    def mercator_y(latitude: float | np.ndarray) -> float | np.ndarray:
        radians = np.radians(np.clip(latitude, -85.05112878, 85.05112878))
        return np.log(np.tan(np.pi / 4.0 + radians / 2.0))

    top_y, bottom_y = float(mercator_y(north)), float(mercator_y(south))
    horizontal_span = np.radians(east - west)
    height = max(2, round(width * (top_y - bottom_y) / horizontal_span))
    destination_y = np.linspace(top_y, bottom_y, height, endpoint=False) - (top_y - bottom_y) / (2.0 * height)
    destination_latitude = np.degrees(2.0 * np.arctan(np.exp(destination_y)) - np.pi / 2.0)
    source_row = np.clip((north - destination_latitude) / (north - south) * native_height - 0.5, 0.0, native_height - 1.0)
    nearest_row = np.rint(source_row).astype(np.int32)
    values = native_values[nearest_row]
    return values.astype(np.float32), [[south, west], [north, east]]


def write_analysis_grid(output: Path, grid_id: str, values: np.ndarray, bounds: list[list[float]]) -> None:
    valid = np.isfinite(values)
    encoded = np.full(values.shape, NODATA, dtype="<u2")
    encoded[valid] = np.rint(np.clip(values[valid], 0, 1) * QUANTIZED_MAXIMUM).astype("<u2")
    payload = {
        "id": grid_id,
        "width": int(values.shape[1]),
        "height": int(values.shape[0]),
        "bounds": bounds,
        "projection": "EPSG:3857",
        "minimum": 0.0,
        "maximum": 1.0,
        "nodata": NODATA,
        "quantizedMaximum": QUANTIZED_MAXIMUM,
        "units": "suitability",
        "data": base64.b64encode(encoded.tobytes(order="C")).decode("ascii"),
    }
    output.write_text(
        "window.SPECIES_ANALYSIS_GRIDS = window.SPECIES_ANALYSIS_GRIDS || {};\n"
        f"window.SPECIES_ANALYSIS_GRIDS[{json.dumps(grid_id)}] = {json.dumps(payload, separators=(',', ':'))};\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--width", type=int, default=0, help="Preview width; 0 retains native width.")
    parser.add_argument(
        "--display-scale",
        type=float,
        default=1.0,
        help="High-density visual enlargement applied after native-grid reprojection; it does not change analytical resolution.",
    )
    parser.add_argument("--analysis-width", type=int, default=1440)
    args = parser.parse_args()

    preview_dir = args.web / "assets" / "species"
    analysis_dir = args.web / "assets" / "species-analysis"
    download_dir = args.web / "assets" / "species-geotiff"
    for directory in (preview_dir, analysis_dir, download_dir):
        directory.mkdir(parents=True, exist_ok=True)
    for old_preview in preview_dir.glob("*.png"):
        old_preview.unlink()
    for old_grid in analysis_dir.glob("*.generated.js"):
        old_grid.unlink()

    species_layers: dict[str, list[dict[str, object]]] = {}
    analysis_manifest: dict[str, dict[str, object]] = {}
    for species_name, folder_name in PREVIEW_SPECIES.items():
        species_dir = args.source / "species_rasters_all" / folder_name
        species_code = file_code(species_name)
        layers: list[dict[str, object]] = []
        for source_code, (public_code, title, title_pt) in LAYER_NAMES.items():
            raster_path = species_dir / f"{folder_name}_{source_code}.tif"
            if not raster_path.is_file():
                raise FileNotFoundError(raster_path)
            output_name = f"{species_code}__{public_code}.png"
            grid_id = f"{slug(species_name)}--{slug(public_code)}"
            grid_name = f"{species_code}__{public_code}.generated.js"
            tif_name = f"{species_code}__{public_code}.tif"
            with rasterio.open(raster_path) as src:
                preview_width = src.width if args.width <= 0 else args.width
                values, leaflet_bounds = web_mercator_preview(src, preview_width)
                valid = np.isfinite(values)
                if not valid.any():
                    raise RuntimeError(f"Preview contains no valid cells: {raster_path}")
                preview_image = colorize(np.nan_to_num(values, nan=0.0), valid)
                if args.display_scale > 1:
                    display_size = (
                        round(preview_image.width * args.display_scale),
                        round(preview_image.height * args.display_scale),
                    )
                    preview_image = preview_image.resize(display_size, Image.Resampling.BICUBIC)
                preview_image.save(preview_dir / output_name, optimize=True)
                analysis_values, _ = web_mercator_preview(src, min(args.analysis_width, src.width))
                write_analysis_grid(analysis_dir / grid_name, grid_id, analysis_values, leaflet_bounds)
                shutil.copy2(raster_path, download_dir / tif_name)
                sampled = values[valid]
                layers.append(
                    {
                        "id": slug(public_code),
                        "gridId": grid_id,
                        "code": public_code,
                        "title": title,
                        "titlePt": title_pt,
                        "image": f"assets/species/{output_name}?v=20260812tools5",
                        "download": f"assets/species-geotiff/{tif_name}",
                        "bounds": leaflet_bounds,
                        "minimum": round(float(np.nanmin(sampled)), 4),
                        "maximum": round(float(np.nanmax(sampled)), 4),
                        "mean": round(float(np.nanmean(sampled)), 4),
                        "previewWidth": int(values.shape[1]),
                        "previewHeight": int(values.shape[0]),
                    }
                )
            analysis_manifest[grid_id] = {"url": f"assets/species-analysis/{grid_name}"}
        species_layers[species_name] = layers

    payload = {
        "period": "1981\u20132024",
        "resolution": "2.5 arc-minutes",
        "domain": "50\u00b0S\u201350\u00b0N",
        "previewSpecies": list(PREVIEW_SPECIES),
        "groups": species_catalog(args.source),
        "speciesLayers": species_layers,
        "analysisManifest": analysis_manifest,
    }
    (args.web / "species.generated.js").write_text(
        "window.SPECIES_SUITABILITY = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"SPECIES_PROTOTYPE_OK={sum(map(len, species_layers.values()))}")
    print(f"PREVIEW_SPECIES={len(species_layers)} EUCALYPTS={len(payload['groups']['eucalypts'])} PINES={len(payload['groups']['pines'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
