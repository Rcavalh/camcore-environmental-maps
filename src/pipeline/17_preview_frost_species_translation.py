from __future__ import annotations

import importlib.util
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap, Normalize
import numpy as np
import pandas as pd


MODULE = Path(__file__).resolve().parents[1]
TABLES = MODULE / "outputs/historical_paired_200000_complete/tables"
FIGURES = MODULE / "outputs/historical_paired_200000_complete/figures"
SURFACE = TABLES / "HISTORICAL_PAIRED_RF_200000_PREDICTIONS.parquet"
HAZARD = TABLES / "HISTORICAL_PAIRED_RF_200000_STATION_DERIVED_BIVARIATE_HAZARD.parquet"
STATIONS = TABLES / "STATION_DERIVED_BIVARIATE_HAZARD_CLIMATOLOGY.csv"

CLASS_LABELS = ["Absent", "Low", "Moderate", "High", "Extreme"]
PRIMARY_PORTFOLIO = [
    "E. urophylla\nE. grandis x E. urophylla",
    "E. grandis\nE. saligna",
    "E. dunnii\nE. globulus\nE. smithii",
    "E. dunnii\nE. nitens",
    "E. benthamii",
]


def load_core():
    path = MODULE / "scripts/08_run_five_state_50000_smoke.py"
    spec = importlib.util.spec_from_file_location("five_state_core_species_preview", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def classify_by_station_quintiles(values: np.ndarray, station_values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cuts = np.quantile(station_values[np.isfinite(station_values)], [0.20, 0.40, 0.60, 0.80])
    return np.digitize(values, cuts, right=False) + 1, cuts


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    core = load_core()
    boundaries = core.load_boundaries()

    surface = pd.read_parquet(SURFACE)
    hazard = pd.read_parquet(HAZARD, columns=["point_id", "hazard_class_typical"])
    surface = surface.merge(hazard, on="point_id", how="left", validate="one_to_one")
    stations = pd.read_csv(STATIONS)

    surface["recurrence_class"], recurrence_cuts = classify_by_station_quintiles(
        surface.expected_frost_days_mean.to_numpy(),
        stations.expected_frost_days.to_numpy(),
    )
    surface["intensity_class"], intensity_cuts_cold = classify_by_station_quintiles(
        -surface.event_minimum_temperature_p25_c.to_numpy(),
        -stations.season_tmin_p25_c.to_numpy(),
    )
    surface["joint_class"] = surface.hazard_class_typical.astype(int)
    surface["portfolio_code"] = surface.joint_class

    agreement = pd.DataFrame({
        "comparison": [
            "recurrence_vs_intensity",
            "recurrence_vs_joint",
            "intensity_vs_joint",
            "all_three",
        ],
        "percent_agreement": [
            100 * np.mean(surface.recurrence_class == surface.intensity_class),
            100 * np.mean(surface.recurrence_class == surface.joint_class),
            100 * np.mean(surface.intensity_class == surface.joint_class),
            100 * np.mean(
                (surface.recurrence_class == surface.intensity_class)
                & (surface.intensity_class == surface.joint_class)
            ),
        ],
    })
    agreement.to_csv(TABLES / "FROST_SPECIES_TRANSLATION_PREVIEW_AGREEMENT.csv", index=False)

    class_rows = []
    for column, approach in [
        ("recurrence_class", "Recurrence only"),
        ("intensity_class", "Intensity only"),
        ("joint_class", "Joint recurrence x intensity"),
    ]:
        counts = surface[column].value_counts().reindex(range(1, 6), fill_value=0)
        for code, count in counts.items():
            class_rows.append({
                "approach": approach,
                "class_id": code,
                "class_label": CLASS_LABELS[code - 1],
                "n_pixels": int(count),
                "percent_pixels": 100 * count / len(surface),
            })
    pd.DataFrame(class_rows).to_csv(TABLES / "FROST_SPECIES_TRANSLATION_PREVIEW_CLASS_SUMMARY.csv", index=False)

    base = plt.get_cmap("RdYlBu")
    colors = [base(value) for value in (0.04, 0.27, 0.50, 0.73, 0.96)]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(np.arange(0.5, 6.0, 1), cmap.N)

    fig, axes = plt.subplots(2, 2, figsize=(13.1, 13.2))
    panels = [
        (axes[0, 0], "intensity_class", "(a) Cold intensity", "P25 seasonal minimum temperature"),
        (axes[0, 1], "recurrence_class", "(b) Frost recurrence", "Mean frost days per season"),
        (axes[1, 0], "joint_class", "(c) Joint frost hazard", "Recurrence x intensity"),
        (axes[1, 1], "portfolio_code", "(d) Primary species portfolio", "Provisional translation of joint classes"),
    ]
    for ax, column, title, subtitle in panels:
        points = ax.scatter(
            surface.longitude,
            surface.latitude,
            c=surface[column],
            s=1.45,
            cmap=cmap,
            norm=norm,
            linewidths=0,
            rasterized=True,
        )
        boundaries.boundary.plot(ax=ax, color="#252525", linewidth=0.58)
        ax.set_title(f"{title}\n{subtitle}", fontsize=11.5)
        ax.set_axis_off()

    risk_cb = fig.colorbar(
        points,
        ax=[axes[0, 0], axes[0, 1], axes[1, 0]],
        fraction=0.025,
        pad=0.012,
        shrink=0.78,
        ticks=range(1, 6),
    )
    risk_cb.ax.set_yticklabels(CLASS_LABELS)
    risk_cb.set_label("Frost-hazard class")

    species_handles = [
        plt.Line2D([0], [0], marker="s", linestyle="none", markersize=8,
                   markerfacecolor=colors[i], markeredgecolor="none",
                   label=f"{CLASS_LABELS[i]}: {PRIMARY_PORTFOLIO[i].replace(chr(10), '; ')}")
        for i in range(5)
    ]
    axes[1, 1].legend(
        handles=species_handles,
        loc="lower left",
        bbox_to_anchor=(-0.04, -0.055),
        frameon=False,
        fontsize=8.0,
        handletextpad=0.5,
    )

    fig.suptitle("Preliminary frost-to-species translation", fontsize=15, y=0.982)
    fig.text(
        0.5,
        0.012,
        "Simulation based on station-derived quintiles over 200,000 modeled pixels. Red = lower and blue = higher frost exposure. "
        "Panel (d) applies the requested primary-species portfolio to the joint class; it is not yet the final occurrence-derived ERA5/BIO6 species match.",
        ha="center",
        fontsize=8.2,
    )
    fig.subplots_adjust(left=0.025, right=0.93, top=0.91, bottom=0.075, wspace=0.12, hspace=0.12)

    light = FIGURES / "FROST_SPECIES_TRANSLATION_PREVIEW_LIGHT.png"
    hd = FIGURES / "FROST_SPECIES_TRANSLATION_PREVIEW_620DPI.png"
    pdf = FIGURES / "FROST_SPECIES_TRANSLATION_PREVIEW.pdf"
    fig.savefig(light, dpi=180, facecolor="white", bbox_inches="tight")
    fig.savefig(hd, dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf, facecolor="white", bbox_inches="tight")
    plt.close(fig)

    print("RECURRENCE_CUTS=" + ",".join(f"{x:.6g}" for x in recurrence_cuts))
    print("INTENSITY_TMIN_CUTS=" + ",".join(f"{-x:.6g}" for x in intensity_cuts_cold))
    print(agreement.to_string(index=False))
    print(f"LIGHT={light}")
    print(f"HD={hd}")
    print(f"PDF={pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
