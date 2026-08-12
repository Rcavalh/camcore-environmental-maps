# Model and data-product methods

## Study domain

The regional prediction domain comprises Rio Grande do Sul, Santa Catarina, Parana, Sao Paulo and Mato Grosso do Sul. The prediction grid follows the native approximately 30 m ANADEM terrain model.

## Predictor blocks

- **Spatial:** latitude and longitude.
- **Terrain and HAND:** elevation, slope, eastness, northness, topographic position, ruggedness, roughness, curvature, local relief, cold-air-pooling context, elevation offsets and HAND calculated with a 2,000 m flow-path definition.
- **ERA5-Land:** a reduced set of thermal, moisture, radiation, wind, pressure and soil-water predictors summarized for 15 May–15 August.
- **MODIS:** quality-screened Terra/Aqua day and night land-surface-temperature summaries and coverage diagnostics.

## Endpoints

- Frost-occurrence probability.
- Expected frost days per eligible season.
- Seasonal minimum temperature in degrees Celsius.

## Model

Separate reduced Random Forest pipelines are fitted for the three endpoints. Predictor selection is performed by scientific block so that the large ERA5-Land block does not dominate merely through feature count. Validation is grouped spatially by station or spatial climate group, preventing observations from the same station from appearing in both training and validation folds.

## Spatial prediction

The fitted models are applied to the ANADEM grid using tiled prediction with persistent checkpoints. Terrain variables provide fine-scale spatial structure; ERA5-Land and MODIS describe the regional atmospheric and surface-thermal environment. Climate predictors are not claimed to have native 30 m resolution: the model estimates local susceptibility conditional on coarse climate and fine physiography.

## Scenarios

The complete-period maps summarize 2000–2025. Period and ENSO maps retain the same fitted model and terrain structure while changing the set of annual climate conditions used in aggregation. The cold-tail temperature product uses the 25th percentile of annual seasonal-minimum-temperature predictions.

## ANADEM provenance

Terrain elevation is derived from ANADEM v1, the approximately 30 m digital terrain model developed for South America by Laipelt et al. (2024). ANADEM removes vegetation-related bias from Copernicus DEM GLO-30 using machine learning, GEDI elevation information and multispectral predictors. The authors report that the data are freely available for use through Google Earth Engine (`projects/et-brasil/assets/anadem/v1`) and MGRS downloads from the official project website.

Reference: Laipelt, L.; de Andrade, B.C.; Collischonn, W.; Teixeira, A.A.; de Paiva, R.C.D.; Ruhoff, A. ANADEM: A Digital Terrain Model for South America. *Remote Sensing* **2024**, *16*, 2321. https://doi.org/10.3390/rs16132321.

## Species Suitability collection

The Species Suitability maps summarize the 1981–2025 climate period at a native resolution of 2.5 arc-minutes. The mapped products represent climatic similarity to the observed natural distribution of each species and include bioclimatic-envelope overlap, Köppen-climate overlap, PCA–Mahalanobis similarity and overall suitability. These scores are screening indices, not direct predictions of survival, productivity or physiological limits.

Methods reference: Cavalheiro, R.; Aguiar, A.M.; Vatsavai, R.R.; et al. A new environmental-based tool to support forest breeders in selecting species adapted to current and near-term climate conditions. *Tree Genetics & Genomes* **2026**, *22*, 16. https://doi.org/10.1007/s11295-026-01741-0.
