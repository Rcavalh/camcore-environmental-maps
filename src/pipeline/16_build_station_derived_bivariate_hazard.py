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
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler


MODULE = Path(__file__).resolve().parents[1]
VALIDATION = MODULE / "outputs/historical_paired_era5_modis_validation/tables/HISTORICAL_ERA5_MODIS_STATION_YEAR_MODELING_TABLE.parquet"
PREDICTIONS = MODULE / "outputs/historical_paired_200000_complete/tables/HISTORICAL_PAIRED_RF_200000_PREDICTIONS.parquet"
TABLES = MODULE / "outputs/historical_paired_200000_complete/tables"
FIGURES = MODULE / "outputs/historical_paired_200000_complete/figures"


CLASS_LABELS = ["Very low", "Low", "Moderate", "High", "Very high"]


def load_core():
    path = MODULE / "scripts/08_run_five_state_50000_smoke.py"
    spec = importlib.util.spec_from_file_location("five_state_core_bivariate_hazard", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def station_climatology() -> pd.DataFrame:
    columns = ["state", "station_id", "year", "frost_days", "frost_any", "observed_season_tmin_c"]
    station_year = pd.read_parquet(VALIDATION, columns=columns)
    climate = (
        station_year.groupby(["state", "station_id"])
        .agg(
            n_years=("year", "nunique"),
            occurrence_probability=("frost_any", "mean"),
            expected_frost_days=("frost_days", "mean"),
            frost_days_p75=("frost_days", lambda values: values.quantile(0.75)),
            season_tmin_p25_c=("observed_season_tmin_c", lambda values: values.quantile(0.25)),
            season_tmin_p05_c=("observed_season_tmin_c", lambda values: values.quantile(0.05)),
        )
        .reset_index()
    )
    return climate.loc[climate.n_years >= 5].dropna().reset_index(drop=True)


def fit_hazard_axis(stations: pd.DataFrame):
    matrix = np.column_stack([
        np.log1p(stations.expected_frost_days.to_numpy()),
        -stations.season_tmin_p25_c.to_numpy(),
    ])
    scaler = StandardScaler().fit(matrix)
    standardized = scaler.transform(matrix)
    pca = PCA(n_components=2).fit(standardized)
    score = pca.transform(standardized)[:, 0]
    if np.corrcoef(score, stations.expected_frost_days)[0, 1] < 0:
        pca.components_[0] *= -1
        score *= -1
    cuts = np.quantile(score, [0.20, 0.40, 0.60, 0.80])
    return scaler, pca, score, cuts


def score_surface(frame: pd.DataFrame, days_column: str, scaler: StandardScaler, pca: PCA) -> np.ndarray:
    matrix = np.column_stack([
        np.log1p(frame[days_column].to_numpy()),
        -frame.event_minimum_temperature_p25_c.to_numpy(),
    ])
    return pca.transform(scaler.transform(matrix))[:, 0]


def class_codes(score: np.ndarray, cuts: np.ndarray) -> np.ndarray:
    return np.digitize(score, cuts, right=False) + 1


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    core = load_core()
    boundaries = core.load_boundaries()
    stations = station_climatology()
    scaler, pca, station_score, cuts = fit_hazard_axis(stations)
    stations["hazard_score"] = station_score
    stations["hazard_class"] = class_codes(station_score, cuts)
    stations["hazard_label"] = stations.hazard_class.map(dict(enumerate(CLASS_LABELS, 1)))

    surface = pd.read_parquet(PREDICTIONS)
    surface["hazard_score_typical"] = score_surface(surface, "expected_frost_days_mean", scaler, pca)
    surface["hazard_score_conservative"] = score_surface(surface, "expected_frost_days_p75", scaler, pca)
    surface["hazard_class_typical"] = class_codes(surface.hazard_score_typical.to_numpy(), cuts)
    surface["hazard_class_conservative"] = class_codes(surface.hazard_score_conservative.to_numpy(), cuts)

    export_columns = [
        "point_id", "state", "longitude", "latitude",
        "annual_frost_probability_mean", "expected_frost_days_mean", "expected_frost_days_p75",
        "event_minimum_temperature_p25_c", "hazard_score_typical", "hazard_class_typical",
        "hazard_score_conservative", "hazard_class_conservative",
    ]
    surface[export_columns].to_parquet(TABLES / "HISTORICAL_PAIRED_RF_200000_STATION_DERIVED_BIVARIATE_HAZARD.parquet", index=False)
    stations.to_csv(TABLES / "STATION_DERIVED_BIVARIATE_HAZARD_CLIMATOLOGY.csv", index=False)

    metadata = pd.DataFrame({
        "parameter": [
            "minimum_station_years", "n_stations", "pc1_explained_variance",
            "pc1_loading_log1p_frost_days", "pc1_loading_cold_intensity",
            "scaler_mean_log1p_frost_days", "scaler_mean_cold_intensity",
            "scaler_scale_log1p_frost_days", "scaler_scale_cold_intensity",
            "score_p20", "score_p40", "score_p60", "score_p80",
        ],
        "value": [
            5, len(stations), pca.explained_variance_ratio_[0],
            pca.components_[0, 0], pca.components_[0, 1],
            scaler.mean_[0], scaler.mean_[1], scaler.scale_[0], scaler.scale_[1],
            *cuts,
        ],
    })
    metadata.to_csv(TABLES / "STATION_DERIVED_BIVARIATE_HAZARD_METHOD.csv", index=False)

    station_summary = (
        stations.groupby(["hazard_class", "hazard_label"], observed=True)
        .agg(
            n_stations=("station_id", "size"),
            frost_days_median=("expected_frost_days", "median"),
            frost_days_q25=("expected_frost_days", lambda x: x.quantile(0.25)),
            frost_days_q75=("expected_frost_days", lambda x: x.quantile(0.75)),
            tmin_p25_median_c=("season_tmin_p25_c", "median"),
            tmin_p25_q25_c=("season_tmin_p25_c", lambda x: x.quantile(0.25)),
            tmin_p25_q75_c=("season_tmin_p25_c", lambda x: x.quantile(0.75)),
            occurrence_probability_median=("occurrence_probability", "median"),
        )
        .reset_index()
    )
    station_summary.to_csv(TABLES / "STATION_DERIVED_BIVARIATE_HAZARD_CLASS_SUMMARY.csv", index=False)

    grid_rows = []
    for scenario, column in [
        ("Typical: mean frost days + P25 Tmin", "hazard_class_typical"),
        ("Conservative: P75 frost days + P25 Tmin", "hazard_class_conservative"),
    ]:
        counts = surface[column].value_counts().reindex(range(1, 6), fill_value=0)
        for code, count in counts.items():
            grid_rows.append({
                "scenario": scenario,
                "hazard_class": code,
                "hazard_label": CLASS_LABELS[code - 1],
                "n_pixels": int(count),
                "percent_pixels": 100 * count / len(surface),
            })
    pd.DataFrame(grid_rows).to_csv(TABLES / "STATION_DERIVED_BIVARIATE_HAZARD_GRID_SUMMARY.csv", index=False)

    base = plt.get_cmap("RdYlBu")
    colors = [base(value) for value in (0.04, 0.27, 0.50, 0.73, 0.96)]
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(np.arange(0.5, 6.0, 1), cmap.N)
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 12.7))

    groups = [stations.loc[stations.hazard_class == code, "expected_frost_days"] for code in range(1, 6)]
    box = axes[0, 0].boxplot(groups, patch_artist=True, tick_labels=CLASS_LABELS, showfliers=False)
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.85)
    axes[0, 0].set_title("(a) Observed frost recurrence by station-derived class")
    axes[0, 0].set_ylabel("Mean frost days per season")
    axes[0, 0].tick_params(axis="x", rotation=18)
    axes[0, 0].grid(axis="y", color="#dddddd", linewidth=0.55)

    groups = [stations.loc[stations.hazard_class == code, "season_tmin_p25_c"] for code in range(1, 6)]
    box = axes[0, 1].boxplot(groups, patch_artist=True, tick_labels=CLASS_LABELS, showfliers=False)
    for patch, color in zip(box["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.85)
    axes[0, 1].set_title("(b) Observed cold intensity by station-derived class")
    axes[0, 1].set_ylabel("P25 seasonal minimum temperature (°C)")
    axes[0, 1].tick_params(axis="x", rotation=18)
    axes[0, 1].grid(axis="y", color="#dddddd", linewidth=0.55)

    map_panels = [
        (axes[1, 0], "hazard_class_typical", "(c) Typical long-term frost hazard"),
        (axes[1, 1], "hazard_class_conservative", "(d) Conservative frost hazard"),
    ]
    for ax, column, title in map_panels:
        points = ax.scatter(
            surface.longitude, surface.latitude, c=surface[column], s=1.4,
            cmap=cmap, norm=norm, linewidths=0, rasterized=True,
        )
        boundaries.boundary.plot(ax=ax, color="#242424", linewidth=0.55)
        ax.set_title(title)
        ax.set_axis_off()

    colorbar = fig.colorbar(points, ax=axes[1, :], fraction=0.028, pad=0.015, shrink=0.82, ticks=range(1, 6))
    colorbar.ax.set_yticklabels(CLASS_LABELS)
    colorbar.set_label("Station-derived recurrence-intensity class")
    fig.suptitle("Data-driven frost-hazard classification from observed station climatology", fontsize=15, y=0.986)
    fig.text(
        0.5, 0.012,
        f"Classes are quintiles of the first principal component of standardized log frost days and cold intensity (-P25 Tmin), derived from {len(stations)} stations with at least five years. "
        f"PC1 explains {100 * pca.explained_variance_ratio_[0]:.1f}% of their joint variance. Red = lower and blue = higher frost hazard.",
        ha="center", fontsize=8.2,
    )
    fig.subplots_adjust(left=0.07, right=0.94, top=0.95, bottom=0.055, wspace=0.16, hspace=0.15)

    light = FIGURES / "STATION_DERIVED_BIVARIATE_FROST_HAZARD_LIGHT.png"
    hd = FIGURES / "STATION_DERIVED_BIVARIATE_FROST_HAZARD_620DPI.png"
    pdf = FIGURES / "STATION_DERIVED_BIVARIATE_FROST_HAZARD.pdf"
    fig.savefig(light, dpi=180, facecolor="white", bbox_inches="tight")
    fig.savefig(hd, dpi=620, facecolor="white", bbox_inches="tight")
    fig.savefig(pdf, facecolor="white", bbox_inches="tight")
    plt.close(fig)

    print(station_summary.to_string(index=False))
    print(f"LIGHT={light}")
    print(f"HD={hd}")
    print(f"PDF={pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
