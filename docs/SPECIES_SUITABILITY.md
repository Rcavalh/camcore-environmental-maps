# Species Suitability collection

## Scope

The Species Suitability collection presents natural-range-based climate-similarity surfaces for plantation-relevant tree species. The current products summarize the 1981–2025 climate period at a native resolution of 2.5 arc-minutes and cover the geographic domain represented by the source rasters.

Four analytical layers are presented where available:

1. **Overall suitability** — combined suitability across the mapped component indices.
2. **Bioclimatic envelope** — proportion of BIO1–BIO19 variables falling within the species-specific central climatic envelope.
3. **Köppen climate overlap** — similarity based on climate-class overlap with the natural distribution.
4. **PCA–Mahalanobis similarity** — multivariate climatic similarity in principal-component space.

Suitability values range from 0 to 1. They describe climatic similarity to observed natural ranges and must not be interpreted as probabilities of survival, productivity forecasts or physiological limits. Deployment decisions should also consider field trials, soils, pests, silviculture, genetic material and local operational knowledge.

## Published methods reference

Cavalheiro, R., Aguiar, A.M., Vatsavai, R.R. *et al.* A new environmental-based tool to support forest breeders in selecting species adapted to current and near-term climate conditions. *Tree Genetics & Genomes* **22**, 16 (2026). https://doi.org/10.1007/s11295-026-01741-0.

## Web visualization and analytical downloads

The portal includes 38 Eucalyptus, 4 Corymbia and 10 Pinus species, presented as three distinct taxonomic groups. It uses Web Mercator WebP previews generated at one-half of the source grid width, together with a numerical inspection grid, so that the complete catalogue remains responsive in a static website. These derivatives are visualization products and do not change the native 2.5-arc-minute analytical resolution of the source GeoTIFFs. Original-resolution analysis should use the downloadable GeoTIFF products.

The high- and low-elevation *Pinus tecunumanii* source variants are retained in the research archive but are not presented as separate species in the public catalogue; the portal exposes the species-level product.

The production architecture separates responsibilities:

- **GitHub Pages:** application code, documentation, catalogues and optimized visualization assets.
- **Persistent data repository:** full-resolution GeoTIFFs, checksums, manifests and versioned data documentation.
- **Portal links:** each map record links to its corresponding analytical download once the persistent dataset identifier is finalized.

This separation prevents large binary rasters from making the Git repository difficult to clone and keeps the web portal below GitHub Pages deployment limits.
