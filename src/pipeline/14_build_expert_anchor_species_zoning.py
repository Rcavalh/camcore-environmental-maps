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


ANCHORS = {
    "Cacador": (-26.819167, -50.985556, "E. benthamii"),
    "Lages": (-27.802222, -50.335556, "E. benthamii"),
    "Canoinhas / Tres Barras": (-26.1648754, -50.4080494, "E. dunnii"),
    "Telemaco Borba": (-24.33, -50.62, "E. urophylla"),
    "Porto Alegre interior": (-30.053611, -51.174722, "E. saligna"),
}


def load_core():
    path = MODULE / "scripts/08_run_five_state_50000_smoke.py"
    spec = importlib.util.spec_from_file_location("five_state_core_anchor_zoning", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def classify(frame: pd.DataFrame) -> np.ndarray:
    """Exploratory expert-anchor calibration, not a validated species recommendation."""
    days = frame["expected_frost_days_mean"].to_numpy()
    tmin = frame["event_minimum_temperature_p25_c"].to_numpy()
    elevation = frame["elevation"].to_numpy()
    probability = frame["annual_frost_probability_mean"].to_numpy()

    # Cut points are midpoints between the environmental medians of the supplied
    # operational anchors. Intensity and recurrence are kept as separate axes.
    zone = np.full(len(frame), "E. urophylla", dtype=object)
    zone[(days >= 4.20) | (probability >= 0.74)] = "E. saligna"
    zone[(days >= 7.94) & (tmin <= -2.0)] = "E. dunnii"
    zone[(days >= 12.63) & ((elevation >= 860) | (tmin <= -3.53))] = "E. benthamii"
    return zone


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    core = load_core()
    boundaries = core.load_boundaries()
    frame = pd.read_parquet(SOURCE)
    frame["expert_anchor_zone"] = classify(frame)

    order = ["E. urophylla", "E. saligna", "E. dunnii", "E. benthamii"]
    codes = pd.Categorical(frame["expert_anchor_zone"], categories=order, ordered=True).codes
    frame["zone_code"] = codes

    overall = frame["expert_anchor_zone"].value_counts().reindex(order, fill_value=0).rename("n_pixels").reset_index()
    overall["percent_pixels"] = 100 * overall["n_pixels"] / len(frame)
    overall.to_csv(TABLES / "SPECIES_ANCHOR_CALIBRATION_PREVIEW_OVERALL.csv", index=False)

    by_state = frame.groupby(["state", "expert_anchor_zone"], observed=False).size().rename("n_pixels").reset_index()
    by_state["percent_within_state"] = by_state.groupby("state")["n_pixels"].transform(lambda x: 100 * x / x.sum())
    by_state.to_csv(TABLES / "SPECIES_ANCHOR_CALIBRATION_PREVIEW_BY_STATE.csv", index=False)

    base = plt.get_cmap("RdYlBu")
    colors = [base(v) for v in (0.05, 0.38, 0.68, 0.95)]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(np.arange(-0.5, 4.5, 1), cmap.N)

    fig, ax = plt.subplots(figsize=(9.1, 10.6))
    points = ax.scatter(
        frame.longitude,
        frame.latitude,
        c=frame.zone_code,
        s=2.0,
        cmap=cmap,
        norm=norm,
        linewidths=0,
        rasterized=True,
    )
    boundaries.boundary.plot(ax=ax, color="#242424", linewidth=0.65)

    for name, (lat, lon, species) in ANCHORS.items():
        ax.scatter(lon, lat, s=34, facecolors="none", edgecolors="#111111", linewidths=1.1, zorder=6)
        dx = 0.10 if name != "Porto Alegre interior" else 0.12
        dy = 0.04 if name != "Lages" else -0.15
        ax.text(lon + dx, lat + dy, f"{name}\n{species}", fontsize=7.6, color="#111111", zorder=7)

    colorbar = fig.colorbar(points, ax=ax, fraction=0.037, pad=0.018, shrink=0.72, ticks=np.arange(4))
    colorbar.ax.set_yticklabels(order)
    colorbar.set_label("Expert-anchor species zone", fontsize=9)
    ax.set_title("Expert-anchor calibration of frost-adapted Eucalyptus zones", fontsize=13, pad=8)
    ax.set_axis_off()
    fig.text(
        0.5,
        0.018,
        "Exploratory calibration from modeled frost recurrence, P25 seasonal minimum temperature and ANADEM elevation.\n"
        "Open circles show the operational anchors supplied by the forest expert; zones are not yet a validated silvicultural recommendation.",
        ha="center",
        fontsize=8.2,
    )
    fig.subplots_adjust(left=0.02, right=0.92, top=0.96, bottom=0.065)

    light = FIGURES / "SPECIES_ANCHOR_CALIBRATION_PREVIEW_LIGHT.png"
    hd = FIGURES / "SPECIES_ANCHOR_CALIBRATION_PREVIEW_620DPI.png"
    pdf = FIGURES / "SPECIES_ANCHOR_CALIBRATION_PREVIEW.pdf"
    fig.savefig(light, dpi=180, facecolor="white", bbox_inches="tight")
    fig.savefig(hd, dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf, facecolor="white", bbox_inches="tight")
    plt.close(fig)

    print(overall.to_string(index=False))
    print(f"LIGHT={light}")
    print(f"HD={hd}")
    print(f"PDF={pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
