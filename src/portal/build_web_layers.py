#!/usr/bin/env python
"""Build web overlays and a grouped layer catalog for the map portal."""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Prefer Rasterio's bundled and version-matched PROJ database before GDAL is
# imported. Some Windows GIS installations set PROJ_LIB globally to an older
# PostGIS database, which breaks reprojection in Python environments.
_RASTERIO_PROJ = Path(sys.prefix) / "Lib" / "site-packages" / "rasterio" / "proj_data"
if (_RASTERIO_PROJ / "proj.db").is_file():
    os.environ["PROJ_LIB"] = str(_RASTERIO_PROJ)
    os.environ["PROJ_DATA"] = str(_RASTERIO_PROJ)

import rasterio
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds, transform_geom
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
PORTAL_ROOT = ROOT.parent
WEB = ROOT / "web"
MODEL_ROOT = PORTAL_ROOT / "dryad_dataset" / "data" / "model_outputs"
V2_ROOT = PORTAL_ROOT / "Zenodo" / "01_Frost_Risk_Maps" / "rasters" / "v2.0"
WATER_MASK_PATH = ROOT / "data" / "masks" / "lagoa_dos_patos_osm_relation_2709093.geojson"
WATER_MASK_ID = "OpenStreetMap relation 2709093 (Lagoa dos Patos)"
ZENODO_RECORD = "https://doi.org/10.5281/zenodo.21918677"
ZENODO_FILES = {
    "frost_probability": "https://zenodo.org/records/21918677/files/FROST_PROBABILITY_MEAN_2000_2026.tif",
    "expected_frost_days": "https://zenodo.org/records/21918677/files/FROST_DAYS_MEAN_2000_2026.tif",
    "seasonal_tmin": "https://zenodo.org/records/21918677/files/TMIN_MEAN_2000_2026.tif",
    "seasonal_tmin_p25": "https://zenodo.org/records/21918677/files/TMIN_P25_2000_2026.tif",
    "hand": "https://zenodo.org/records/21918677/files/HAND_2000M.tif",
}


ENDPOINTS = {
    "probability": {
        "title": "Frost-occurrence probability",
        "titlePt": "Probabilidade de ocorrência de geada",
        "cmap": "RdYlBu",
        "fixed_range": [0.0, 1.0],
        "units": "probability",
        "filename": "frost_probability",
    },
    "frost_days": {
        "title": "Expected frost days per season",
        "titlePt": "Dias esperados de geada por temporada",
        "cmap": "RdYlBu",
        "percentiles": [0.5, 99.5],
        "units": "days season⁻¹",
        "filename": "expected_frost_days",
    },
    "tmin_mean": {
        "title": "Seasonal minimum temperature — mean",
        "titlePt": "Temperatura mínima sazonal — média",
        "cmap": "RdYlBu_r",
        "percentiles": [0.5, 99.5],
        "units": "°C",
        "filename": "seasonal_minimum_temperature_mean",
    },
    "tmin_p25": {
        "title": "Seasonal minimum temperature — P25",
        "titlePt": "Temperatura mínima sazonal — P25",
        "cmap": "RdYlBu_r",
        "percentiles": [0.5, 99.5],
        "units": "°C",
        "filename": "seasonal_minimum_temperature_p25",
    },
}


def load_water_geometry_3857() -> dict:
    """Load the static Lagoa dos Patos polygon and project it to web-map CRS."""
    payload = json.loads(WATER_MASK_PATH.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    if len(features) != 1:
        raise RuntimeError(f"Expected one water-mask feature in {WATER_MASK_PATH}")
    return transform_geom(
        "EPSG:4326", "EPSG:3857", features[0]["geometry"], precision=-1
    )


WATER_GEOMETRY_3857 = load_water_geometry_3857()


def model_spec(
    *,
    layer_id: str,
    endpoint: str,
    source: Path,
    output: str,
    group: str,
    scenario: str,
    scenario_label: str,
    scenario_label_pt: str,
    subtitle: str,
    subtitle_pt: str,
    max_width: int,
    analysis_width: int,
) -> dict:
    metadata = ENDPOINTS[endpoint]
    return {
        "id": layer_id,
        "endpoint": endpoint,
        "title": metadata["title"],
        "titlePt": metadata["titlePt"],
        "subtitle": subtitle,
        "subtitlePt": subtitle_pt,
        "source": source,
        "output": output,
        "cmap": metadata["cmap"],
        "units": metadata["units"],
        "status": "complete five-state analytical surface",
        "statusPt": "superfície analítica completa para os cinco estados",
        # Only complete-period files are deposited in the current Zenodo record.
        # Other displayed scenarios link to the record landing page in the portal.
        "download": ZENODO_FILES.get(layer_id, ZENODO_RECORD),
        "group": group,
        "scenario": scenario,
        "scenarioLabel": scenario_label,
        "scenarioLabelPt": scenario_label_pt,
        "max_width": max_width,
        "analysis_width": analysis_width,
        **({"fixed_range": metadata["fixed_range"]} if "fixed_range" in metadata else {}),
        **({"percentiles": metadata["percentiles"]} if "percentiles" in metadata else {}),
    }


def build_layer_specs() -> list[dict]:
    specs: list[dict] = []
    complete_defs = [
        (
            "frost_probability", "probability",
            "RF_DIRECT_GRIDS_FROST_PROBABILITY_MEAN_ALL_2000_2026_FIVE_STATES_HAND15_ANADEM30M.tif",
            "frost_probability_2000_2026_v2.png",
        ),
        (
            "expected_frost_days", "frost_days",
            "RF_DIRECT_GRIDS_EXPECTED_FROST_DAYS_MEAN_ALL_2000_2026_FIVE_STATES_HAND15_ANADEM30M.tif",
            "expected_frost_days_2000_2026_v2.png",
        ),
        (
            "seasonal_tmin", "tmin_mean",
            "RF_DIRECT_GRIDS_SEASONAL_MINIMUM_TEMPERATURE_C_MEAN_ALL_2000_2026_FIVE_STATES_HAND15_ANADEM30M.tif",
            "seasonal_minimum_temperature_mean_2000_2026_v2.png",
        ),
        (
            "seasonal_tmin_p25", "tmin_p25",
            "RF_DIRECT_GRIDS_SEASONAL_MINIMUM_TEMPERATURE_C_P25_ALL_2000_2026_FIVE_STATES_HAND15_ANADEM30M.tif",
            "seasonal_minimum_temperature_p25_2000_2026_v2.png",
        ),
    ]
    for layer_id, endpoint, filename, output in complete_defs:
        specs.append(model_spec(
            layer_id=layer_id, endpoint=endpoint, source=V2_ROOT / filename,
            output=output, group="complete", scenario="2000_2026_v2",
            scenario_label="2000–2026 · v2.0", scenario_label_pt="2000–2026 · v2.0",
            subtitle="Version 2.0 complete-period climatology · 2000–2026",
            subtitle_pt="Climatologia v2.0 do período completo · 2000–2026",
            max_width=6000, analysis_width=2048,
        ))

    enso_defs = [
        ("el_nino", "El Niño", "El Niño"),
        ("la_nina", "La Niña", "La Niña"),
        ("neutral", "Neutral", "Neutro"),
    ]
    for scenario, label, label_pt in enso_defs:
        candidates = [
            (
                "probability",
                V2_ROOT / f"RF_DIRECT_GRIDS_FROST_PROBABILITY_MEAN_ENSO_{scenario.upper()}_FIVE_STATES_HAND15_ANADEM30M.tif",
            ),
            (
                "tmin_p25",
                V2_ROOT / f"RF_DIRECT_GRIDS_SEASONAL_MINIMUM_TEMPERATURE_C_P25_ENSO_{scenario.upper()}_FIVE_STATES_HAND15_ANADEM30M.tif",
            ),
        ]
        # Source filenames use EL_NINO and LA_NINA, matching the upper-case IDs above.
        for endpoint, source in candidates:
            if not source.is_file():
                continue
            specs.append(model_spec(
                layer_id=f"enso_{scenario}_{endpoint}", endpoint=endpoint, source=source,
                output=f"enso_{scenario}_{endpoint}.png", group="enso", scenario=scenario,
                scenario_label=label, scenario_label_pt=label_pt,
                subtitle=f"ENSO-conditioned climatology · {label}",
                subtitle_pt=f"Climatologia condicionada ao ENSO · {label_pt}",
                max_width=6000, analysis_width=2048,
            ))

    for spec in specs:
        spec["status"] = "version 2.0 complete five-state analytical surface"
        spec["statusPt"] = "superfície analítica v2.0 completa para os cinco estados"

    specs.extend([
        {
            "id": "hand", "endpoint": "hand", "title": "Height above nearest drainage",
            "titlePt": "Altura acima da drenagem mais próxima",
            "subtitle": "HAND · 2-km flow-path search", "subtitlePt": "HAND · busca de fluxo de 2 km",
            "source": PORTAL_ROOT / "00_HAND" / "anadem_rs_pr_sc_sp_ms_30m_HAND_flowpath_within_2000m_filled_zero.tif",
            "output": "hand_2000m.png", "cmap": "viridis", "percentiles": [1.0, 99.0],
            "units": "m", "status": "derived terrain layer", "statusPt": "camada derivada do terreno",
            "download": ZENODO_FILES["hand"],
            "group": "terrain", "scenario": "hand", "scenarioLabel": "HAND", "scenarioLabelPt": "HAND",
            "max_width": 6000, "analysis_width": 2048,
        },
        {
            "id": "anadem", "endpoint": "elevation", "title": "Terrain elevation",
            "titlePt": "Elevação do terreno",
            "subtitle": "ANADEM v1 digital terrain model", "subtitlePt": "Modelo digital de terreno ANADEM v1",
            "source": PORTAL_ROOT / "00_ANADEM_DEM" / "ANADEM_v1_30m_RS_PR_SC_SP_MS_recortado.tif",
            "output": "anadem_elevation.png", "cmap": "viridis", "percentiles": [0.5, 99.5],
            "units": "m a.s.l.", "status": "third-party source layer; cite Laipelt et al. (2024)",
            "statusPt": "camada de terceiros; cite Laipelt et al. (2024)",
            "download": "https://hge-iph.github.io/anadem/", "group": "terrain", "scenario": "elevation",
            "scenarioLabel": "Elevation", "scenarioLabelPt": "Elevação",
            "max_width": 6000, "analysis_width": 2048,
        },
    ])
    return specs


LAYER_SPECS = build_layer_specs()


def rgba_from_raster(spec: dict, max_width: int) -> tuple[np.ndarray, dict]:
    with rasterio.open(spec["source"]) as src:
        if src.crs is None:
            raise RuntimeError(f"Raster has no CRS: {spec['source']}")

        # Leaflet displays image overlays in Web Mercator. Reprojecting the preview
        # before creating the PNG prevents the north-south displacement produced by
        # stretching a regular latitude/longitude raster over a Mercator basemap.
        with WarpedVRT(
            src,
            crs="EPSG:3857",
            resampling=Resampling.bilinear,
            nodata=src.nodata,
        ) as web:
            scale = min(1.0, max_width / web.width)
            out_width = max(1, int(round(web.width * scale)))
            out_height = max(1, int(round(web.height * scale)))
            data = web.read(1, out_shape=(out_height, out_width), masked=True)
            preview_transform = web.transform * Affine.scale(
                web.width / out_width, web.height / out_height
            )
            west, south, east, north = transform_bounds(
                web.crs, "EPSG:4326", *web.bounds, densify_pts=21
            )
        values = np.asarray(data.filled(np.nan), dtype="float32")
        valid = np.isfinite(values)
        if src.nodata is not None and np.isfinite(src.nodata):
            valid &= values != src.nodata

        # The analytical surfaces cover the complete rectangular raster domain.
        # Explicitly remove the lake so no frost/terrain value is shown over water.
        water = geometry_mask(
            [WATER_GEOMETRY_3857],
            out_shape=values.shape,
            transform=preview_transform,
            invert=True,
            all_touched=False,
        )
        masked_water_cells = int(np.count_nonzero(valid & water))
        valid &= ~water

        finite = values[valid]
        if finite.size == 0:
            raise RuntimeError(f"No valid cells in {spec['source']}")
        if "fixed_range" in spec:
            vmin, vmax = spec["fixed_range"]
        else:
            vmin, vmax = np.nanpercentile(finite, spec["percentiles"])
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
            raise RuntimeError(f"Invalid display range for {spec['source']}: {vmin}, {vmax}")

        normalized = np.clip((values - vmin) / (vmax - vmin), 0, 1)
        rgba = plt.get_cmap(spec["cmap"])(np.nan_to_num(normalized, nan=0.0), bytes=True)
        rgba[..., 3] = np.where(valid, 238, 0).astype("uint8")
        metadata = {
            "bounds": [[south, west], [north, east]],
            "nativeWidth": src.width, "nativeHeight": src.height,
            "previewWidth": out_width, "previewHeight": out_height,
            "crs": src.crs.to_string() if src.crs else None,
            "previewCrs": "EPSG:3857",
            "nativeResolution": list(src.res),
            "displayMin": round(float(vmin), 4), "displayMax": round(float(vmax), 4),
            "validPercent": round(float(valid.mean() * 100), 3),
            "waterMask": WATER_MASK_ID,
            "waterMaskedCells": masked_water_cells,
        }
        return rgba, metadata


def render_layer(spec: dict, width: int, output: Path) -> dict:
    rgba, metadata = rgba_from_raster(spec, width)
    Image.fromarray(rgba, mode="RGBA").save(output, optimize=True)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-width", type=int, default=6000)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()

    out_dir = WEB / "assets" / "layers"
    out_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = WEB / "layers.json"
    try:
        previous_catalog = {item["id"]: item for item in json.loads(catalog_path.read_text(encoding="utf-8"))}
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        previous_catalog = {}

    metadata: dict[str, dict] = {}
    pending = []
    for spec in LAYER_SPECS:
        if not spec["source"].is_file():
            raise FileNotFoundError(spec["source"])
        output = out_dir / spec["output"]
        cached = previous_catalog.get(spec["id"])
        requested = min(args.max_width, spec["max_width"])
        expected_width = min(requested, cached.get("nativeWidth", 0) if cached else 0)
        can_reuse = (
            output.is_file() and cached is not None and cached.get("palette") == spec["cmap"]
            and cached.get("previewWidth") == expected_width
            and cached.get("previewCrs") == "EPSG:3857"
            and cached.get("waterMask") == WATER_MASK_ID
            and output.stat().st_mtime >= spec["source"].stat().st_mtime
            and output.stat().st_mtime >= WATER_MASK_PATH.stat().st_mtime
        )
        if can_reuse:
            metadata[spec["id"]] = {key: cached[key] for key in (
                "bounds", "nativeWidth", "nativeHeight", "previewWidth", "previewHeight",
                "crs", "previewCrs", "nativeResolution", "displayMin", "displayMax", "validPercent",
                "waterMask", "waterMaskedCells"
            )}
            print(f"WEB_LAYER_REUSED={output}")
        else:
            pending.append((spec, requested, output))

    if pending:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {executor.submit(render_layer, spec, width, output): (spec, output) for spec, width, output in pending}
            for future in as_completed(futures):
                spec, output = futures[future]
                metadata[spec["id"]] = future.result()
                print(f"WEB_LAYER_RENDERED={output}")

    catalog = []
    for spec in LAYER_SPECS:
        meta = metadata[spec["id"]]
        catalog.append({
            "id": spec["id"], "endpoint": spec["endpoint"], "title": spec["title"],
            "titlePt": spec["titlePt"], "subtitle": spec["subtitle"], "subtitlePt": spec["subtitlePt"],
            "url": f"assets/layers/{spec['output']}", "units": spec["units"],
            "status": spec["status"], "statusPt": spec["statusPt"], "palette": spec["cmap"],
            "download": spec["download"], "group": spec["group"], "scenario": spec["scenario"],
            "scenarioLabel": spec["scenarioLabel"], "scenarioLabelPt": spec["scenarioLabelPt"],
            **meta,
        })
        print(f"WEB_LAYER_OK={spec['id']} ({meta['previewWidth']}x{meta['previewHeight']})")

    catalog_json = json.dumps(catalog, indent=2, ensure_ascii=False)
    catalog_path.write_text(catalog_json, encoding="utf-8")
    (WEB / "layers.generated.js").write_text(f"window.FROST_LAYERS = {catalog_json};\n", encoding="utf-8")
    print(f"WEB_LAYER_CATALOG_OK={catalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
