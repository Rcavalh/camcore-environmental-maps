from __future__ import annotations

import importlib.util
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd


MODULE = Path(__file__).resolve().parents[1]
TABLES = MODULE / "outputs/historical_paired_200000_complete/tables"
FIGURES = MODULE / "outputs/historical_paired_200000_complete/figures"
SOURCE = TABLES / "HISTORICAL_PAIRED_RF_200000_PREDICTIONS.parquet"
ANCHORS_SOURCE = TABLES / "SPECIES_EXPERT_MUNICIPAL_ANCHORS_IBGE.csv"


CONFIRMED = {
    "Guarapuava": "E. benthamii",
    "Cacador": "E. benthamii",
    "Lages": "E. benthamii",
    "Timbo Grande": "E. benthamii",
    "Sao Joao do Triunfo": "E. dunnii",
    "Sao Mateus do Sul": "E. dunnii",
    "Canoinhas": "E. dunnii",
    "Mafra": "E. dunnii",
    "Doutor Pedrinho": "E. grandis",
    "Telemaco Borba": "E. grandis x E. urophylla",
}
CANDIDATE = {"Santa Maria": "E. dunnii?", "Capao Bonito": "E. dunnii?"}


def ascii_name(value: str) -> str:
    import unicodedata

    return "".join(
        char for char in unicodedata.normalize("NFD", str(value))
        if unicodedata.category(char) != "Mn"
    )


def load_core():
    path = MODULE / "scripts/08_run_five_state_50000_smoke.py"
    spec = importlib.util.spec_from_file_location("five_state_core_expanded_anchor", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def classify(frame: pd.DataFrame) -> np.ndarray:
    days = frame["expected_frost_days_mean"].to_numpy()
    tmin = frame["event_minimum_temperature_p25_c"].to_numpy()
    elevation = frame["elevation"].to_numpy()
    probability = frame["annual_frost_probability_mean"].to_numpy()

    # Midpoints between the median environmental profiles of confirmed anchors:
    # urograndis -> grandis -> dunnii, with elevation separating benthamii from
    # lower-elevation dunnii environments of similar thermal intensity.
    zone = np.full(len(frame), "E. grandis x E. urophylla", dtype=object)
    zone[(days >= 4.37) | (probability >= 0.758)] = "E. grandis"
    cold = (days >= 7.57) & (tmin <= -1.85)
    zone[cold] = "E. dunnii"
    zone[cold & (elevation >= 945)] = "E. benthamii"
    return zone


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    core = load_core()
    boundaries = core.load_boundaries()
    frame = pd.read_parquet(SOURCE)
    anchors = pd.read_csv(ANCHORS_SOURCE)
    anchors["ascii_name"] = anchors.municipality.map(ascii_name)
    anchors["status"] = np.where(anchors.ascii_name.isin(CONFIRMED), "confirmed", "candidate")
    anchors["expert_species"] = anchors.ascii_name.map({**CONFIRMED, **CANDIDATE})

    order = ["E. grandis x E. urophylla", "E. grandis", "E. dunnii", "E. benthamii"]
    frame["expert_anchor_zone"] = classify(frame)
    frame["zone_code"] = pd.Categorical(frame.expert_anchor_zone, categories=order, ordered=True).codes

    overall = frame.expert_anchor_zone.value_counts().reindex(order, fill_value=0).rename("n_pixels").reset_index()
    overall["percent_pixels"] = 100 * overall.n_pixels / len(frame)
    overall.to_csv(TABLES / "SPECIES_EXPANDED_ANCHOR_CALIBRATION_OVERALL.csv", index=False)
    by_state = frame.groupby(["state", "expert_anchor_zone"], observed=False).size().rename("n_pixels").reset_index()
    by_state["percent_within_state"] = by_state.groupby("state").n_pixels.transform(lambda x: 100 * x / x.sum())
    by_state.to_csv(TABLES / "SPECIES_EXPANDED_ANCHOR_CALIBRATION_BY_STATE.csv", index=False)

    base = plt.get_cmap("RdYlBu")
    cmap = ListedColormap([base(v) for v in (0.05, 0.38, 0.68, 0.95)])
    norm = BoundaryNorm(np.arange(-0.5, 4.5, 1), cmap.N)
    fig, ax = plt.subplots(figsize=(9.6, 10.7))
    points = ax.scatter(
        frame.longitude, frame.latitude, c=frame.zone_code, s=2.0,
        cmap=cmap, norm=norm, linewidths=0, rasterized=True,
    )
    boundaries.boundary.plot(ax=ax, color="#242424", linewidth=0.65)

    confirmed = anchors[anchors.status == "confirmed"]
    candidate = anchors[anchors.status == "candidate"]
    ax.scatter(confirmed.longitude, confirmed.latitude, s=28, marker="o", facecolors="none", edgecolors="#111111", linewidths=1.0, zorder=6)
    ax.scatter(candidate.longitude, candidate.latitude, s=34, marker="D", facecolors="none", edgecolors="#111111", linewidths=1.0, zorder=6)
    for _, row in anchors.iterrows():
        dx, dy = 0.08, 0.04
        if row.ascii_name == "Santa Maria":
            dx, dy = 0.12, -0.18
        elif row.ascii_name == "Capao Bonito":
            dx, dy = 0.10, 0.08
        elif row.ascii_name in {"Cacador", "Timbo Grande", "Canoinhas"}:
            dx, dy = 0.09, -0.10
        ax.text(row.longitude + dx, row.latitude + dy, row.municipality, fontsize=6.8, color="#111111", zorder=7)

    colorbar = fig.colorbar(points, ax=ax, fraction=0.037, pad=0.018, shrink=0.72, ticks=np.arange(4))
    colorbar.ax.set_yticklabels(order)
    colorbar.set_label("Expert-anchor species zone", fontsize=9)
    handles = [
        Line2D([0], [0], marker="o", color="none", markeredgecolor="#111111", markerfacecolor="none", markersize=6, label="Confirmed operational anchor"),
        Line2D([0], [0], marker="D", color="none", markeredgecolor="#111111", markerfacecolor="none", markersize=6, label="Candidate location to validate"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=8)
    ax.set_title("Expanded expert-anchor calibration of Eucalyptus frost zones", fontsize=13, pad=8)
    ax.set_axis_off()
    fig.text(
        0.5, 0.016,
        "Exploratory zones derived from modeled frost recurrence, P25 seasonal minimum temperature and ANADEM elevation.\n"
        "Santa Maria and Capao Bonito remain candidate checks; the current environmental model does not classify their full municipal surroundings as E. dunnii.",
        ha="center", fontsize=8.0,
    )
    fig.subplots_adjust(left=0.02, right=0.92, top=0.96, bottom=0.065)

    light = FIGURES / "SPECIES_EXPANDED_ANCHOR_CALIBRATION_LIGHT.png"
    hd = FIGURES / "SPECIES_EXPANDED_ANCHOR_CALIBRATION_620DPI.png"
    pdf = FIGURES / "SPECIES_EXPANDED_ANCHOR_CALIBRATION.pdf"
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
