# Camcore Environmental Maps

<p align="center">
  <img src="web/assets/images/CAMCORE_LOGO_TRANSPARENT.png" alt="Camcore" width="210">
</p>

<p align="center">
  <a href="https://rcavalh.github.io/camcore-environmental-maps/"><strong>Open the interactive map portal</strong></a>
</p>

<p align="center">
  <a href="https://doi.org/10.5281/zenodo.21981334"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.21981334.svg" alt="Frost Climatology dataset DOI"></a>
  <a href="https://doi.org/10.5281/zenodo.21939047"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.21939047.svg" alt="Species Suitability dataset DOI"></a>
</p>

Reproducible code, metadata and lightweight previews for Camcore environmental map collections. Repository documentation is maintained in English. The interactive portal retains its English/Portuguese language selector.

## Map collections

- **[Frost Climatology](docs/METHODS.md)** - frost-occurrence probability, expected frost days, seasonal minimum temperature and terrain context for Rio Grande do Sul, Santa Catarina, Parana, Sao Paulo and Mato Grosso do Sul. The current production contract covers 2000-2026.
- **[Species Suitability](docs/SPECIES_SUITABILITY.md)** - natural-range-based climatic suitability surfaces for Eucalyptus, Corymbia and Pinus.
- **[Bioclimatic Variables](docs/BIOCLIMATIC_VARIABLES.md)** - BIO1-BIO19 temperature and precipitation layers for 1981-2025.
- **[Heat Maps](docs/HEAT_MAPS.md)** - monthly P95 maximum-temperature climatologies.
- **[Camcore Tested Provenances](docs/TESTED_PROVENANCES.md)** - mapped origins represented in Camcore provenance testing.

## Frost Climatology workflow

<p align="center">
  <a href="docs/METHODS.md#workflow-overview">
    <img src="docs/images/FROST_CLIMATOLOGY_ANALYTICAL_WORKFLOW.png" alt="Reproducible analytical workflow for Frost Climatology" width="760">
  </a>
</p>

<p align="center"><sub>Weather-station observations, environmental predictors, Random Forest modelling and spatial map products. Select the diagram for the complete methods.</sub></p>

## Frost Climatology production contract

The station-based Random Forest workflow models three complementary endpoints:

1. frost-occurrence probability;
2. expected frost days per eligible season;
3. seasonal minimum temperature, including P25 cold-tail summaries.

The final HAND15 model uses 115 ordered predictors and a 15 km downstream HAND flow-path support radius. Annual ERA5-Land and MODIS grids are aligned directly to the ANADEM terrain grid; station-based inverse-distance interpolation and post-prediction spatial smoothing are not used. Fine-scale spatial variation therefore comes from ANADEM terrain and HAND, while ERA5-Land and MODIS retain their regional information content.

The canonical production matrix is [`data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv`](data/model_matrix/RF_MODEL_INPUT_HAND15_V2_2001_2026.csv). It contains 2,693 eligible station-seasons, 219 stations, three observed responses and exactly the 115 ordered predictors used by the final Random Forest. The accompanying raw matrix preserves pre-imputation missingness for leakage-free grouped validation. Company damage observations are excluded.

## Reproducibility

- **Workstation - Python:** [`local/python`](local/python)
- **Workstation - R:** [`local/R`](local/R)
- **HPC - LSF/Hazel:** [`hpc`](hpc)
- **Exact production scripts:** [`src/pipeline`](src/pipeline)
- **HAND15 derivation:** [`src/hand15`](src/hand15)
- **Feature manifest:** [`metadata/FINAL_BLOCK_BALANCED_FEATURES.csv`](metadata/FINAL_BLOCK_BALANCED_FEATURES.csv)

Start with [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md), [`docs/METHODS.md`](docs/METHODS.md) and [`local/README.md`](local/README.md).

Public documentation uses **preflight validation** for input/dependency checks, **reduced-scale integration check** for a small end-to-end execution and **spatial cross-validation** for scientific model assessment. Historical filenames containing `smoke` are retained only for provenance and compatibility with completed runs.

## Data availability

The repository contains code, metadata, the model-ready station matrix and lightweight web products. Authoritative analytical GeoTIFFs are archived on Zenodo:

- Frost Climatology: [10.5281/zenodo.21981334](https://doi.org/10.5281/zenodo.21981334)
- Species Suitability: [10.5281/zenodo.21939047](https://doi.org/10.5281/zenodo.21939047)

Third-party datasets retain their original licences and distribution terms. ANADEM should be cited as Laipelt et al. (2024), *Remote Sensing* **16**, 2321, [10.3390/rs16132321](https://doi.org/10.3390/rs16132321).

## Citation and contributors

Repository citation metadata are provided in [`CITATION.cff`](CITATION.cff). Contributor information is recorded in [`CONTRIBUTORS.md`](CONTRIBUTORS.md). Manuscript authorship is established separately.

Species Suitability users should cite:

> Cavalheiro, R., Aguiar, A.M., Vatsavai, R.R. *et al.* A new environmental-based tool to support forest breeders in selecting species adapted to current and near-term climate conditions. *Tree Genetics & Genomes* **22**, 16 (2026). [10.1007/s11295-026-01741-0](https://doi.org/10.1007/s11295-026-01741-0).

## Repository structure

```text
config/         portable path templates
data/           public model-ready matrices and lightweight supporting data
docs/           collection methods, provenance and reproducibility
hpc/            LSF production workflow
local/python/   portable Python implementation
local/R/        portable R implementation
metadata/       feature manifests and scenario definitions
src/hand15/     GRASS/R workflow for the 15 km HAND layer
src/pipeline/   frozen production scripts
web/            bilingual GitHub Pages portal
```

Code licensing remains pending author approval. No credentials or machine-specific private paths belong in the public repository.
