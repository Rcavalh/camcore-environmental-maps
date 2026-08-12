from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import PowerNorm
from rasterio.enums import Resampling


HAND_DIR = Path(os.environ.get("FROST_HAND_DIR", "/path/to/HAND"))
HAND_PATH = HAND_DIR / "anadem_rs_pr_sc_sp_ms_30m_HAND_flowpath_within_2000m_filled_zero.tif"
OUT_DIR = HAND_DIR / "inspection"

PROJECT = Path(os.environ.get("FROST_PROJECT_ROOT", "/path/to/frost-risk-project"))
MET_ROOT = PROJECT / "8.Dados_Meteorologicos_Publicos"
BOUNDARIES = {
    "MS": MET_ROOT / "07_RS_SP_MS_Extension/boundaries/ibge_MS_minimum.geojson",
    "SP": MET_ROOT / "07_RS_SP_MS_Extension/boundaries/ibge_SP_minimum.geojson",
    "PR": MET_ROOT / "boundaries/ibge_PR_minimum.geojson",
    "SC": MET_ROOT / "boundaries/ibge_SC_minimum.geojson",
    "RS": MET_ROOT / "07_RS_SP_MS_Extension/boundaries/ibge_RS_minimum.geojson",
}


def read_boundaries(target_crs):
    frames = []
    for state, path in BOUNDARIES.items():
        frame = gpd.read_file(path)
        if frame.crs is None:
            frame = frame.set_crs("EPSG:4674")
        if target_crs is not None:
            frame = frame.to_crs(target_crs)
        frame = frame[["geometry"]].copy()
        frame["state"] = state
        frames.append(frame)
    return gpd.GeoDataFrame(
        np.concatenate([f.to_records(index=False) for f in frames]),
        columns=["geometry", "state"],
        geometry="geometry",
        crs=frames[0].crs,
    )


def state_coverage(preview, transform, states):
    from rasterio.features import geometry_mask

    finite = np.isfinite(preview)
    rows = []
    for state in states["state"]:
        shape = states.loc[states["state"] == state, "geometry"].iloc[0]
        inside = geometry_mask(
            [shape.__geo_interface__],
            out_shape=preview.shape,
            transform=transform,
            invert=True,
        )
        n_inside = int(inside.sum())
        n_valid = int((inside & finite).sum())
        values = preview[inside & finite]
        rows.append(
            {
                "state": state,
                "preview_pixels_inside_state": n_inside,
                "preview_pixels_with_hand": n_valid,
                "preview_valid_percent": round(100 * n_valid / n_inside, 3) if n_inside else np.nan,
                "preview_hand_median_m": round(float(np.nanmedian(values)), 3) if values.size else np.nan,
                "preview_hand_p95_m": round(float(np.nanpercentile(values, 95)), 3) if values.size else np.nan,
            }
        )
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not HAND_PATH.exists():
        raise FileNotFoundError(HAND_PATH)

    with rasterio.open(HAND_PATH) as src:
        target_width = 2400
        target_height = max(1, round(src.height * target_width / src.width))
        preview_ma = src.read(
            1,
            out_shape=(target_height, target_width),
            masked=True,
            resampling=Resampling.nearest,
        )
        preview_raw = preview_ma.filled(np.nan).astype("float32")
        # User-provided semantic contract: zeros were written into source NA
        # cells. They are therefore missing coverage, not true HAND = 0 m.
        preview = np.where(preview_raw == 0, np.nan, preview_raw)
        preview_transform = src.transform * src.transform.scale(
            src.width / target_width, src.height / target_height
        )
        bounds = src.bounds
        raster_crs = src.crs
        tags = src.tags()
        profile = src.profile

    finite_raw_values = preview_raw[np.isfinite(preview_raw)]
    finite_values = preview[np.isfinite(preview)]
    if finite_values.size == 0:
        raise RuntimeError("The HAND raster contains no valid cells in the preview sample.")

    quantile_probs = [0, 0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99, 1]
    quantiles = np.quantile(finite_values, quantile_probs)
    display_max = float(np.quantile(finite_values, 0.99))
    positive = finite_values[finite_values > 0]

    # The file encodes SIRGAS 2000 geographic coordinates, but its WKT omits the
    # standard datum/spheroid names. EPSG:4674 is used only for boundary overlay.
    boundary_crs = raster_crs if raster_crs is not None else "EPSG:4674"
    states = read_boundaries(boundary_crs)
    coverage_rows = state_coverage(preview, preview_transform, states)

    audit = {
        "source_path": str(HAND_PATH),
        "file_size_bytes": HAND_PATH.stat().st_size,
        "file_size_gib": round(HAND_PATH.stat().st_size / 1024**3, 3),
        "driver": profile["driver"],
        "bands": profile["count"],
        "dtype": profile["dtype"],
        "width": profile["width"],
        "height": profile["height"],
        "total_cells": int(profile["width"] * profile["height"]),
        "crs_wkt": raster_crs.to_wkt() if raster_crs else None,
        "crs_epsg_identified": raster_crs.to_epsg() if raster_crs else None,
        "crs_interpretation": "SIRGAS 2000 geographic; normalize metadata to EPSG:4674 before production use",
        "bounds": {"left": bounds.left, "bottom": bounds.bottom, "right": bounds.right, "top": bounds.top},
        "resolution_degrees": {"x": abs(profile["transform"].a), "y": abs(profile["transform"].e)},
        "approx_resolution_m_at_center_latitude": {
            "x": abs(profile["transform"].a) * 111_320 * math.cos(math.radians((bounds.bottom + bounds.top) / 2)),
            "y": abs(profile["transform"].e) * 110_574,
        },
        "nodata": str(profile["nodata"]),
        "compression": profile.get("compress"),
        "tiled": profile.get("tiled"),
        "blockxsize": profile.get("blockxsize"),
        "blockysize": profile.get("blockysize"),
        "overview_count": 0,
        "preview_sampling": f"nearest-neighbor decimation to {target_width} x {target_height}",
        "zero_semantics": "Source value 0 represents filled NA and is masked from analysis and mapping",
        "preview_raw_non_nodata_cells": int(finite_raw_values.size),
        "preview_zero_filled_na_cells": int(np.sum(finite_raw_values == 0)),
        "preview_zero_filled_na_percent_among_raw_non_nodata": round(100 * np.mean(finite_raw_values == 0), 3),
        "preview_valid_positive_hand_cells": int(finite_values.size),
        "preview_valid_percent_of_bbox": round(100 * finite_values.size / preview.size, 3),
        "preview_positive_min_m": float(np.min(positive)) if positive.size else None,
        "preview_mean_m": float(np.mean(finite_values)),
        "preview_sd_m": float(np.std(finite_values)),
        "preview_quantiles_m": {str(p): float(q) for p, q in zip(quantile_probs, quantiles)},
        "display_clipping": f"0 to preview P99 ({display_max:.2f} m); cells above P99 retain the top color",
        "source_tags": tags,
        "state_coverage_preview": coverage_rows,
    }

    with (OUT_DIR / "NEW_HAND_RASTER_AUDIT.json").open("w", encoding="utf-8") as handle:
        json.dump(audit, handle, indent=2, ensure_ascii=False)

    with (OUT_DIR / "NEW_HAND_STATE_COVERAGE_AUDIT.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(coverage_rows[0].keys()))
        writer.writeheader()
        writer.writerows(coverage_rows)

    # Publication map. Power normalization preserves drainage-bottom detail while
    # retaining the full 0-P99 metric range. Original values are not transformed.
    fig = plt.figure(figsize=(8.4, 10.0))
    ax = fig.add_axes([0.10, 0.105, 0.72, 0.82])
    cax = fig.add_axes([0.855, 0.25, 0.028, 0.52])
    hand_cmap = plt.get_cmap("viridis").copy()
    hand_cmap.set_bad("#d9d9d9")
    image = ax.imshow(
        preview,
        extent=(bounds.left, bounds.right, bounds.bottom, bounds.top),
        origin="upper",
        cmap=hand_cmap,
        norm=PowerNorm(gamma=0.55, vmin=0, vmax=display_max, clip=True),
        interpolation="nearest",
    )
    states.boundary.plot(ax=ax, color="#202020", linewidth=0.65, zorder=3)
    for _, row in states.iterrows():
        pt = row.geometry.representative_point()
        ax.text(
            pt.x,
            pt.y,
            row.state,
            ha="center",
            va="center",
            fontsize=10,
            color="white",
            weight="bold",
            path_effects=[],
            bbox={"boxstyle": "round,pad=0.18", "facecolor": "black", "edgecolor": "none", "alpha": 0.55},
            zorder=4,
        )
    cb = fig.colorbar(image, cax=cax)
    cb.set_label("Height above nearest drainage (m)", fontsize=11)
    cb.ax.tick_params(labelsize=9)
    ax.set_title("Height above nearest drainage across southern and southeastern Brazil", fontsize=15, pad=12)
    ax.text(
        0.0,
        -0.080,
        f"ANADEM-derived HAND; 2,000 m flow-path threshold; native resolution ≈ 30 m. "
        f"Source zeros are masked as filled NoData; colors clipped at P99 = {display_max:.1f} m.",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.5,
        color="#333333",
    )
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    center_lat = (bounds.bottom + bounds.top) / 2
    ax.set_aspect(1 / math.cos(math.radians(center_lat)))
    ax.set_xlim(bounds.left, bounds.right)
    ax.set_ylim(bounds.bottom, bounds.top)
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.65)
        spine.set_color("#444444")

    light_path = OUT_DIR / "NEW_HAND_RS_PR_SC_SP_MS_MAP_LIGHT.png"
    hd_path = OUT_DIR / "NEW_HAND_RS_PR_SC_SP_MS_MAP_620DPI.png"
    pdf_path = OUT_DIR / "NEW_HAND_RS_PR_SC_SP_MS_MAP.pdf"
    fig.savefig(light_path, dpi=160, facecolor="white", bbox_inches="tight")
    fig.savefig(hd_path, dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)

    print(json.dumps({
        "status": "NEW_HAND_INSPECTION_OK",
        "audit": str(OUT_DIR / "NEW_HAND_RASTER_AUDIT.json"),
        "coverage": str(OUT_DIR / "NEW_HAND_STATE_COVERAGE_AUDIT.csv"),
        "light_map": str(light_path),
        "hd_map": str(hd_path),
        "pdf_map": str(pdf_path),
    }, indent=2))


if __name__ == "__main__":
    main()
