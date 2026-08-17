#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) stop("Usage: audit_multistate_dem.R DEM.tif OUTPUT.csv")
suppressPackageStartupMessages(library(terra))

dem_path <- normalizePath(args[[1]], mustWork = TRUE)
output_path <- args[[2]]
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
dem <- rast(dem_path)
if (nlyr(dem) != 1L) stop("The multi-state ANADEM must contain exactly one band")
e <- ext(dem)
geographic <- is.lonlat(dem)
if (geographic) {
  if (any(res(dem) < 0.0002 | res(dem) > 0.0004)) {
    stop("Expected an approximately 30 m geographic ANADEM grid; found ",
         paste(res(dem), collapse = " x "), " degrees")
  }
  latitudes <- c(south = ymin(e), center = (ymin(e) + ymax(e)) / 2, north = ymax(e))
  ns_m <- rep(res(dem)[2] * 111132, length(latitudes))
  names(ns_m) <- names(latitudes)
  ew_m <- res(dem)[1] * 111320 * cos(latitudes * pi / 180)
  cell_area_m2 <- ns_m * ew_m
  resolution_x_center_m <- unname(ew_m[["center"]])
  resolution_y_center_m <- unname(ns_m[["center"]])
  width_km <- (xmax(e) - xmin(e)) * 111320 * cos(mean(latitudes) * pi / 180) / 1000
  height_km <- (ymax(e) - ymin(e)) * 111132 / 1000
} else {
  if (any(res(dem) < 25 | res(dem) > 35)) {
    stop("Expected an approximately 30 m projected ANADEM grid; found ",
         paste(res(dem), collapse = " x "), " map units")
  }
  resolution_x_center_m <- res(dem)[1]
  resolution_y_center_m <- res(dem)[2]
  cell_area_m2 <- rep(prod(res(dem)), 3)
  names(cell_area_m2) <- c("south", "center", "north")
  width_km <- (xmax(e) - xmin(e)) / 1000
  height_km <- (ymax(e) - ymin(e)) / 1000
}
audit <- data.frame(
  dem = dem_path,
  bands = nlyr(dem), rows = nrow(dem), columns = ncol(dem),
  cells = ncell(dem),
  grid_type = if (geographic) "geographic_sirgas2000_native" else "projected_metric_native",
  native_resolution_x = res(dem)[1], native_resolution_y = res(dem)[2],
  resolution_x_center_m = resolution_x_center_m,
  resolution_y_center_m = resolution_y_center_m,
  cell_area_south_m2 = unname(cell_area_m2[["south"]]),
  cell_area_center_m2 = unname(cell_area_m2[["center"]]),
  cell_area_north_m2 = unname(cell_area_m2[["north"]]),
  threshold_2000_cells_south_km2 = unname(cell_area_m2[["south"]]) * 2000 / 1e6,
  threshold_2000_cells_center_km2 = unname(cell_area_m2[["center"]]) * 2000 / 1e6,
  threshold_2000_cells_north_km2 = unname(cell_area_m2[["north"]]) * 2000 / 1e6,
  xmin = xmin(e), xmax = xmax(e), ymin = ymin(e), ymax = ymax(e),
  width_km_approx = width_km,
  height_km_approx = height_km,
  uncompressed_float64_gib_per_raster = ncell(dem) * 8 / 1024^3,
  crs = crs(dem, proj = TRUE),
  stringsAsFactors = FALSE
)
write.csv(audit, output_path, row.names = FALSE)
cat("MULTISTATE_ANADEM_INPUT_AUDIT_OK\n")
if (geographic) {
  cat("GRID_NOTE=Native geographic SIRGAS 2000 retained; GRASS reports geodesic distances in meters.\n")
  cat("THRESHOLD_NOTE=The physical area represented by 2000 cells varies with latitude; see audit CSV.\n")
}
print(audit[, setdiff(names(audit), c("dem", "crs"))])
