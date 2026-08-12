from __future__ import annotations

import importlib.util
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
import numpy as np
import pandas as pd


MODULE = Path(__file__).resolve().parents[1]
SOURCE = MODULE / "outputs/historical_paired_200000_complete/tables/HISTORICAL_PAIRED_RF_200000_PREDICTIONS.parquet"
FIGURES = MODULE / "outputs/historical_paired_200000_complete/figures"
TABLES = MODULE / "outputs/historical_paired_200000_complete/tables"


def load_core():
    path = MODULE / "scripts/08_run_five_state_50000_smoke.py"
    spec = importlib.util.spec_from_file_location("five_state_core_replot", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> int:
    core = load_core()
    boundaries = core.load_boundaries()
    frame = pd.read_parquet(SOURCE)
    geo = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(frame.longitude, frame.latitude), crs=4326)

    cold_year_tmin = frame["event_minimum_temperature_p25_c"]
    labels = ["Absent", "Low", "Moderate", "High", "Extreme"]
    primary_species = [
        "E. urophylla; E. grandis x E. urophylla",
        "E. grandis; E. saligna",
        "E. dunnii; E. globulus; E. smithii",
        "E. dunnii; E. nitens",
        "E. benthamii",
    ]
    additional_species = [
        "E. grandis; E. robusta",
        "E. grandis x E. urophylla; E. robusta",
        "E. amplifolia",
        "E. viminalis; E. badjensis",
        "E. dorrigoensis; E. macarthurii; E. benthamii x E. dunnii",
    ]
    codes = pd.cut(
        cold_year_tmin,
        bins=[-np.inf, -3.0, -2.0, -1.0, 0.0, np.inf],
        labels=[4, 3, 2, 1, 0],
        include_lowest=True,
        right=True,
    ).astype(int).to_numpy()
    geo["frost_severity_class"] = codes

    summary = pd.DataFrame({
        "class_id": np.arange(1, 6),
        "class_label": labels,
        "temperature_interval_c": ["> 0", "-1 to 0", "-2 to -1", "-3 to -2", "≤ -3"],
        "primary_commercial_species": primary_species,
        "additional_candidate_species": additional_species,
        "n_pixels": [(codes == idx).sum() for idx in range(5)],
    })
    summary["percent_pixels"] = 100 * summary.n_pixels / len(geo)
    summary.to_csv(TABLES / "HISTORICAL_PAIRED_RF_200000_SPECIES_SUITABILITY_CLASS_SUMMARY.csv", index=False)

    continuous_cmap = "RdYlBu"
    temperature_cmap = "RdYlBu_r"
    categorical_colors = [plt.get_cmap("RdYlBu")(value) for value in np.linspace(0.04, 0.96, 5)]
    categorical_cmap = ListedColormap(categorical_colors)
    categorical_norm = BoundaryNorm(np.arange(-0.5, 5.5, 1), categorical_cmap.N)

    fig, axes = plt.subplots(2, 2, figsize=(12.4, 13.0))
    panels = [
        ("annual_frost_probability_mean", "(a) Mean annual frost probability", "Probability", continuous_cmap, 0, 1),
        ("expected_frost_days_mean", "(b) Expected frost days per season", "Days", continuous_cmap, 0, None),
        ("event_minimum_temperature_mean_c", "(c) Seasonal minimum temperature", "Temperature (°C)", temperature_cmap, None, None),
    ]
    for ax, (column, title, colorbar_label, cmap, vmin, vmax) in zip(axes.ravel()[:3], panels):
        scatter = ax.scatter(
            geo.longitude, geo.latitude, c=geo[column], s=1.35,
            cmap=cmap, vmin=vmin, vmax=vmax, linewidths=0, rasterized=True,
        )
        boundaries.boundary.plot(ax=ax, color="#222222", linewidth=0.55)
        ax.set_title(title, fontsize=12)
        ax.set_axis_off()
        colorbar = fig.colorbar(scatter, ax=ax, fraction=0.035, pad=0.015, shrink=0.78)
        colorbar.set_label(colorbar_label, fontsize=9)

    ax = axes.ravel()[3]
    categorical = ax.scatter(
        geo.longitude, geo.latitude, c=geo.frost_severity_class, s=1.35,
        cmap=categorical_cmap, norm=categorical_norm, linewidths=0, rasterized=True,
    )
    boundaries.boundary.plot(ax=ax, color="#222222", linewidth=0.55)
    ax.set_title("(d) Frost-risk classes and primary species", fontsize=12)
    ax.set_axis_off()
    colorbar = fig.colorbar(categorical, ax=ax, fraction=0.035, pad=0.015, shrink=0.78, ticks=np.arange(5))
    colorbar.ax.set_yticklabels([
        "Absent  > 0°C\nE. urophylla; E. grandis x E. urophylla",
        "Low  -1 to 0°C\nE. grandis; E. saligna",
        "Moderate  -2 to -1°C\nE. dunnii; E. globulus; E. smithii",
        "High  -3 to -2°C\nE. dunnii; E. nitens",
        "Extreme  ≤ -3°C\nE. benthamii",
    ])
    colorbar.set_label("P25 seasonal minimum temperature and primary species", fontsize=9)

    fig.suptitle("Historical paired Random Forest — 200,000 spatial samples", fontsize=16, y=0.985)
    fig.text(
        0.5, 0.012,
        "ANADEM terrain, HAND, ERA5-Land and QC-filtered MODIS paired by year and 15 May–15 August season (2000–2025); panel (d) uses P25 of annual seasonal Tmin; red = lower and blue = higher frost severity.",
        ha="center", fontsize=8.5,
    )
    fig.subplots_adjust(left=0.025, right=0.965, top=0.955, bottom=0.04, wspace=0.12, hspace=0.08)
    light = FIGURES / "HISTORICAL_PAIRED_RF_200000_SPECIES_ZONING_LIGHT.png"
    hd = FIGURES / "HISTORICAL_PAIRED_RF_200000_SPECIES_ZONING_620DPI.png"
    pdf = FIGURES / "HISTORICAL_PAIRED_RF_200000_SPECIES_ZONING.pdf"
    fig.savefig(light, dpi=160, facecolor="white", bbox_inches="tight")
    fig.savefig(hd, dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(summary.to_string(index=False).replace("≤", "<="))
    print(f"LIGHT={light}")
    print(f"HD={hd}")
    print(f"PDF={pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
