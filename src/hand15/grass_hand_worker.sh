#!/usr/bin/env bash
# Runs inside an initialized GRASS location. Do not call directly.
set -euo pipefail
: "${HAND_DEM:?}" "${HAND_OUTPUT_DIR:?}" "${HAND_LABEL:?}" "${HAND_STREAM_AREA_KM2:?}" "${HAND_MEMORY_MB:?}"
threshold_tag="${HAND_THRESHOLD_TAG:-50k}"

export GRASS_OVERWRITE=1
r.in.gdal input="$HAND_DEM" output=dem_native --overwrite
g.region raster=dem_native -a
eval "$(g.region -g)"
native_nsres="$nsres"; native_ewres="$ewres"
# In a latitude/longitude project, -m reports geodesic resolution in meters.
# The center-of-region cell area gives an explicit approximation for converting
# a physical contributing area to r.watershed's cell-count threshold.
eval "$(g.region -gm)"
nsres_m="$nsres"; ewres_m="$ewres"
cell_area_m2="$(awk -v ns="$nsres_m" -v ew="$ewres_m" 'BEGIN {printf "%.12f", ns*ew}')"
threshold_cells="$(awk -v km2="$HAND_STREAM_AREA_KM2" -v area="$cell_area_m2" 'BEGIN {v=(km2*1000000)/area; if(v<1)v=1; printf "%d", v+0.5}')"
threshold_basis="physical contributing area converted to cells"
if [[ -n "${HAND_STREAM_THRESHOLD_CELLS:-}" ]]; then
  threshold_cells="$HAND_STREAM_THRESHOLD_CELLS"
  threshold_basis="explicit cell threshold"
fi
threshold_area_km2_approx="$(awk -v n="$threshold_cells" -v area="$cell_area_m2" 'BEGIN {printf "%.6f", n*area/1000000}')"
radius_products_m="$(printf '%s\n' "$HAND_FLOWPATH_RADII_M" | awk '{$1=$1; gsub(/ /,";"); print}')"

# Use the student's map names and exact r.watershed sequence. Keeping the
# stream and drainage rasters from the same call is essential for matching the
# reference HAND.
flowacc_map="flowacc_${threshold_tag}"
drainage_map="drainage_${threshold_tag}"
streams_map="streams_${threshold_tag}"
above_stream_map="above_stream_${threshold_tag}"
watershed_flags=()
watershed_storage_mode="ram"
if [[ "${HAND_WATERSHED_DISK_SWAP:-0}" == "1" ]]; then
  watershed_flags+=("-m")
  watershed_storage_mode="seg_disk_swap"
fi
r.watershed "${watershed_flags[@]}" elevation=dem_native threshold="$threshold_cells" \
  accumulation="$flowacc_map" drainage="$drainage_map" stream="$streams_map" \
  memory="$HAND_MEMORY_MB" --overwrite

stream_source="DEM-derived r.watershed streams (student exact)"
stream_map="$streams_map"
direction_map="$drainage_map"
if [[ "${HAND_STUDENT_EXACT:-1}" != "1" && -n "${HAND_HYDRO:-}" ]]; then
  # v.import reprojects when the vector CRS differs from the DEM project.
  v.import input="$HAND_HYDRO" output=hydrography --overwrite
  v.to.rast input=hydrography output=streams_observed_raw type=line use=val value=1 --overwrite
  r.mapcalc "streams_observed = if(streams_observed_raw > 0, 1, null())" --overwrite
  stream_map="streams_observed"
  stream_source="supplied hydrography rasterized on native grid"
fi

# Install neither software nor add-ons silently. Use r.hand when available;
# otherwise the documented r.stream.distance difference output is equivalent
# elevation above the downstream stream along the flow direction.
hand_module=""
if command -v r.stream.distance >/dev/null 2>&1; then
  if [[ "${HAND_STUDENT_EXACT:-1}" == "1" ]]; then
    # Exact command supplied by the student: do not add another output or
    # substitute r.hand, because reproducibility is the purpose of this mode.
    r.stream.distance stream_rast="$streams_map" direction="$drainage_map" elevation=dem_native \
      method=downstream difference="$above_stream_map" memory="$HAND_MEMORY_MB" --overwrite
  else
    r.stream.distance stream_rast="$stream_map" direction="$direction_map" elevation=dem_native \
      method=downstream difference="$above_stream_map" distance=flow_distance_to_drainage_m \
      memory="$HAND_MEMORY_MB" --overwrite
  fi
  hand_module="r.stream.distance method=downstream difference (student/reference workflow)"
elif [[ "${HAND_STUDENT_EXACT:-1}" != "1" ]] && command -v r.hand >/dev/null 2>&1; then
  r.hand elevation=dem_native streams="$stream_map" direction="$direction_map" \
    hand="$above_stream_map" memory="$HAND_MEMORY_MB" --overwrite
  hand_module="r.hand fallback"
else
  echo "Neither r.hand nor r.stream.distance is installed in GRASS_ADDON_BASE." >&2
  echo "Install once with: g.extension extension=r.hand && g.extension extension=r.stream.distance" >&2
  exit 3
fi

# Preserve the student's above_stream result and calculate distance in a
# separate call. These four masks use downstream flow-path distance, which is
# hydrologically more precise than Euclidean distance to a vector line.
r.stream.distance stream_rast="$streams_map" direction="$drainage_map" elevation=dem_native \
  method=downstream distance=flow_distance_to_drainage_m \
  memory="$HAND_MEMORY_MB" --overwrite
for radius in $HAND_FLOWPATH_RADII_M; do
  r.mapcalc "hand_flowpath_within_${radius}m = if(flow_distance_to_drainage_m <= ${radius}, ${above_stream_map}, null())" --overwrite
done
if [[ "${HAND_EXPORT_FILLED_ZERO:-0}" == "1" ]]; then
  for radius in $HAND_FLOWPATH_RADII_M; do
    # Fill only inside valid DEM support. Cells outside the source DEM remain
    # NoData; masked/negative HAND cells inside the DEM become explicit zero.
    r.mapcalc "hand_flowpath_within_${radius}m_filled_zero = if(isnull(dem_native), null(), if(isnull(hand_flowpath_within_${radius}m), 0.0, max(hand_flowpath_within_${radius}m, 0.0)))" --overwrite
  done
fi

if [[ "${HAND_STUDENT_EXACT:-1}" != "1" ]]; then
  # Experimental products are deliberately excluded from student-exact mode.
  r.mapcalc "stream_elevation = if(!isnull($stream_map), dem_native, null())" --overwrite
  r.grow.distance -m input=stream_elevation distance=euclidean_distance_to_drainage_m \
    value=nearest_drainage_elevation_m metric=euclidean --overwrite
  for radius in $HAND_PROXY_RADII_M; do
    r.mapcalc "hand_proxy_nearest_drainage_${radius}m = if(euclidean_distance_to_drainage_m <= ${radius}, max(dem_native - nearest_drainage_elevation_m, 0.0), null())" --overwrite
  done
fi

export_raster() {
  local map="$1" file="$2" data_type="${3:-Float32}" nodata_value="${4:--9999}"
  local creation_options="${5:-COMPRESS=DEFLATE,TILED=YES,BIGTIFF=YES}"
  # -f acknowledges the deliberate output type. Float32 gives sub-millimetre
  # numerical resolution over the HAND elevation range while keeping the very
  # large native rasters compact. Accumulation remains Float64 and D8 direction
  # is stored losslessly as Int16.
  # -c suppresses the GRASS color table. Float64/Int16 scientific GeoTIFFs do
  # not need it, and GDAL otherwise prints a misleading SetColorTable ERROR 6.
  r.out.gdal -f -c input="$map" output="${HAND_OUTPUT_DIR}/${file}" format=GTiff \
    type="$data_type" nodata="$nodata_value" createopt="$creation_options" --overwrite
}
# Student-compatible principal HAND: Float64, NaN NoData, scanline GeoTIFF,
# native DEM geometry, and BigTIFF support. This matches the existing HAND
# rasters under data/03_hand rather than the compact auxiliary raster profile.
if [[ "${HAND_EXPORT_AUXILIARY:-1}" == "1" ]]; then
  export_raster "$above_stream_map" "${HAND_LABEL}_HAND_flowpath_GRASS_native.tif" Float64 nan "BIGTIFF=YES"
  export_raster "$above_stream_map" "${HAND_LABEL}_above_stream_${threshold_tag}.tif" Float64 nan "BIGTIFF=YES"
  export_raster "$drainage_map" "${HAND_LABEL}_flow_direction_SFD.tif" Int16
  export_raster "$flowacc_map" "${HAND_LABEL}_flow_accumulation.tif" Float64
  export_raster flow_distance_to_drainage_m "${HAND_LABEL}_flowpath_distance_to_drainage_m.tif" Float64
fi
for radius in $HAND_FLOWPATH_RADII_M; do
  export_raster "hand_flowpath_within_${radius}m" "${HAND_LABEL}_HAND_flowpath_within_${radius}m.tif" Float64 nan "BIGTIFF=YES"
done
if [[ "${HAND_EXPORT_FILLED_ZERO:-0}" == "1" ]]; then
  for radius in $HAND_FLOWPATH_RADII_M; do
    export_raster "hand_flowpath_within_${radius}m_filled_zero" \
      "${HAND_LABEL}_HAND_flowpath_within_${radius}m_filled_zero.tif" \
      Float64 nan "COMPRESS=DEFLATE,TILED=YES,BIGTIFF=YES,PREDICTOR=3"
  done
fi
if [[ "${HAND_STUDENT_EXACT:-1}" != "1" ]]; then
  export_raster euclidean_distance_to_drainage_m "${HAND_LABEL}_euclidean_distance_to_drainage_m.tif"
  for radius in $HAND_PROXY_RADII_M; do
    export_raster "hand_proxy_nearest_drainage_${radius}m" "${HAND_LABEL}_HAND_proxy_nearest_drainage_${radius}m.tif"
  done
fi

# Student-compatible thin drainage Shapefile derived from the exact raster
# stream cells used as HAND targets.
if [[ "${HAND_EXPORT_STREAM_VECTOR:-1}" == "1" ]]; then
  r.thin input="$stream_map" output=streams_native_thin_raster --overwrite
  r.to.vect input=streams_native_thin_raster output=streams_native_thin type=line --overwrite
  v.out.ogr input=streams_native_thin \
    output="${HAND_OUTPUT_DIR}/streams_${HAND_LABEL}_thin.shp" \
    format=ESRI_Shapefile --overwrite
fi

{
  echo "label,dem,native_ns_resolution,native_ew_resolution,center_ns_resolution_m,center_ew_resolution_m,stream_source,threshold_basis,requested_stream_area_km2,stream_threshold_cells,approx_stream_area_km2,hand_module,student_exact,watershed_storage_mode,principal_hand_dtype,principal_hand_nodata,principal_hand_layout,stream_vector_format,radius_definition,radius_products_m,auxiliary_exports,stream_vector_export,filled_zero_exports"
  echo "${HAND_LABEL},${HAND_DEM},${native_nsres},${native_ewres},${nsres_m},${ewres_m},${stream_source},${threshold_basis},${HAND_STREAM_AREA_KM2},${threshold_cells},${threshold_area_km2_approx},${hand_module},${HAND_STUDENT_EXACT:-1},${watershed_storage_mode},Float64,NaN,scanline_uncompressed_BigTIFF,ESRI_Shapefile,student_HAND_masked_by_downstream_flowpath_distance,${radius_products_m},${HAND_EXPORT_AUXILIARY:-1},${HAND_EXPORT_STREAM_VECTOR:-1},${HAND_EXPORT_FILLED_ZERO:-0}"
} > "${HAND_OUTPUT_DIR}/${HAND_LABEL}_HAND_GRASS_manifest.csv"
r.univar -g map="$above_stream_map" > "${HAND_OUTPUT_DIR}/${HAND_LABEL}_HAND_flowpath_GRASS_stats.txt"
for radius in $HAND_FLOWPATH_RADII_M; do
  r.univar -g map="hand_flowpath_within_${radius}m" > "${HAND_OUTPUT_DIR}/${HAND_LABEL}_HAND_flowpath_within_${radius}m_stats.txt"
done
if [[ "${HAND_EXPORT_FILLED_ZERO:-0}" == "1" ]]; then
  for radius in $HAND_FLOWPATH_RADII_M; do
    r.univar -g map="hand_flowpath_within_${radius}m_filled_zero" > \
      "${HAND_OUTPUT_DIR}/${HAND_LABEL}_HAND_flowpath_within_${radius}m_filled_zero_stats.txt"
  done
fi
if [[ "${HAND_STUDENT_EXACT:-1}" != "1" ]]; then
  for radius in $HAND_PROXY_RADII_M; do
    r.univar -g map="hand_proxy_nearest_drainage_${radius}m" > "${HAND_OUTPUT_DIR}/${HAND_LABEL}_HAND_proxy_${radius}m_stats.txt"
  done
fi
