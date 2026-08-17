# Model and data-product methods

## Workflow overview

![Reproducible analytical workflow for frost climatology](images/FROST_CLIMATOLOGY_ANALYTICAL_WORKFLOW.png)

The diagram summarizes the Frost Climatology collection from weather-station responses and environmental predictors through station-grouped validation, interpretation and spatial deployment. It is maintained with the collection methods rather than on the repository homepage.

## Production contract

The current production workflow is **article version 2.2 (HAND15 direct grids)**. It covers Rio Grande do Sul, Santa Catarina, Parana, Sao Paulo and Mato Grosso do Sul on the native approximately 30 m ANADEM grid. Climate maps summarize 2000-2026. The available INMET response table contains 2,693 eligible station-seasons from 219 stations in 2001-2026; no response label was fabricated for 2000.

The frost season is fixed at 15 May-15 August. Three responses are modelled independently:

1. `frost_any`: occurrence of at least one observed frost day in the season;
2. `frost_days`: observed number of frost days in the season;
3. `observed_season_tmin_c`: observed seasonal minimum air temperature (degrees Celsius).

## Predictor contract

The final model uses 115 ordered predictors. The machine-readable source of truth is [`metadata/FINAL_BLOCK_BALANCED_FEATURES.csv`](../metadata/FINAL_BLOCK_BALANCED_FEATURES.csv).

- **Spatial, terrain and HAND (19):** latitude, longitude, year, elevation, slope, eastness, northness, native TPI, TRI and roughness, plan/profile/surface curvature, and five 2 km local-terrain summaries plus HAND.
- **ERA5-Land (64):** selected frost-season atmospheric, surface and soil summaries.
- **MODIS (32):** quality-screened Terra/Aqua surface-temperature, vegetation and retrieval-coverage summaries.

Two distances must not be conflated. Local relief, cold-air-pooling and elevation-offset variables retain their 2,000 m neighbourhood. Only HAND uses the updated **15,000 m downstream flow-path support radius**. Drainage initiation remains fixed at 2,000 contributing cells.

The distributed zero-filled HAND raster uses zero for unresolved support cells. During station extraction, values that are non-finite or less than or equal to zero are therefore restored to missing; they are never interpreted as genuine valley-bottom observations. Predictor missingness is retained in the public raw matrix. Median imputation is estimated using training data only within each validation fold and is fitted on the complete training matrix only for the final production model. A separate canonical post-imputation matrix records the exact float32 values consumed during that final refit.

## Climate assignment: direct grids, not station IDW

Version 2.2 removed the former station-to-map inverse-distance-weighted climate reconstruction. Annual ERA5-Land and MODIS frost-season stacks are read directly, reprojected to the ANADEM grid and supplied to the fitted model at each terrain pixel. Continuous layers are aligned bilinearly; discrete and count layers use nearest-neighbour alignment. This direct-grid contract eliminates the triangular spatial artifacts associated with station IDW. It does not claim that ERA5-Land or MODIS have native 30 m resolution: fine spatial structure comes from ANADEM/HAND while the climate layers retain their regional information content.

No spatial smoothing is applied after prediction.

## Random Forest fitting and validation

The final Random Forest comprises one classifier and two regressors:

- occurrence classifier: 900 trees, maximum depth 18, minimum leaf size 5, square-root feature sampling and balanced subsampling;
- frost-day regressor: 700 trees, Poisson criterion, minimum leaf size 4 and 45% feature sampling;
- minimum-temperature regressor: 700 trees, squared-error criterion, minimum leaf size 4 and 45% feature sampling.

Before the final fit, an Extra Trees classifier ranks candidate predictors. All spatial/terrain/HAND variables are retained, while the 64 highest-ranked ERA5-Land and 32 highest-ranked MODIS variables are selected. During scientific evaluation, both selection and imputation are repeated within each training fold. Five-fold grouped cross-validation holds out complete station identities (`state + station_id`), so years from a held-out station never enter its training folds.

## Spatial products and scenarios

The fitted models are applied tile by tile to every valid ANADEM cell. The complete-period products are mean annual frost probability, mean expected frost days, mean seasonal minimum temperature and the P25 of annual seasonal-minimum-temperature predictions. ENSO products retain the fitted model and static terrain but aggregate annual predictions within El Nino, La Nina and neutral year groups.

## ANADEM provenance

Terrain elevation is derived from ANADEM v1, the approximately 30 m digital terrain model for South America developed by Laipelt et al. (2024). ANADEM removes vegetation-related bias from Copernicus DEM GLO-30 using machine learning, GEDI elevation information and multispectral predictors.

Reference: Laipelt, L.; de Andrade, B.C.; Collischonn, W.; Teixeira, A.A.; de Paiva, R.C.D.; Ruhoff, A. ANADEM: A Digital Terrain Model for South America. *Remote Sensing* **2024**, *16*, 2321. https://doi.org/10.3390/rs16132321.

## Species Suitability collection

The Species Suitability maps summarize the 1981-2025 climate period at a native resolution of 2.5 arc-minutes. They represent climatic similarity to observed natural distributions and are screening indices rather than direct predictions of survival, productivity or physiological limits.

Methods reference: Cavalheiro, R.; Aguiar, A.M.; Vatsavai, R.R.; et al. A new environmental-based tool to support forest breeders in selecting species adapted to current and near-term climate conditions. *Tree Genetics & Genomes* **2026**, *22*, 16. https://doi.org/10.1007/s11295-026-01741-0.
