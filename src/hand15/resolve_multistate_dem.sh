#!/usr/bin/env bash
set -euo pipefail

resolve_multistate_dem() {
  local vrt_output="$1"
  if [[ -n "${MULTISTATE_ANADEM_DEM:-}" ]]; then
    [[ -s "$MULTISTATE_ANADEM_DEM" ]] || {
      echo "Explicit multi-state DEM does not exist: $MULTISTATE_ANADEM_DEM" >&2
      return 2
    }
    MULTISTATE_ANADEM_DEM="$(cd "$(dirname "$MULTISTATE_ANADEM_DEM")" && pwd)/$(basename "$MULTISTATE_ANADEM_DEM")"
    export MULTISTATE_ANADEM_DEM
    echo "MULTISTATE_DEM_RESOLVED mode=explicit path=$MULTISTATE_ANADEM_DEM"
    return 0
  fi

  [[ -d "${MULTISTATE_ANADEM_DIR:-}" ]] || {
    echo "Multi-state ANADEM directory does not exist: ${MULTISTATE_ANADEM_DIR:-unset}" >&2
    return 2
  }
  mapfile -t candidates < <(
    find "$MULTISTATE_ANADEM_DIR" -maxdepth 1 -type f \
      \( -iname '*.tif' -o -iname '*.tiff' \) -print | sort
  )
  ((${#candidates[@]} > 0)) || {
    echo "No GeoTIFF found in $MULTISTATE_ANADEM_DIR" >&2
    return 2
  }
  if ((${#candidates[@]} == 1)); then
    MULTISTATE_ANADEM_DEM="${candidates[0]}"
    export MULTISTATE_ANADEM_DEM
    echo "MULTISTATE_DEM_RESOLVED mode=single_geotiff path=$MULTISTATE_ANADEM_DEM"
    return 0
  fi

  command -v gdalbuildvrt >/dev/null || {
    echo "Multiple GeoTIFFs found, but gdalbuildvrt is unavailable." >&2
    return 3
  }
  mkdir -p "$(dirname "$vrt_output")"
  gdalbuildvrt -overwrite "$vrt_output" "${candidates[@]}"
  MULTISTATE_ANADEM_DEM="$(cd "$(dirname "$vrt_output")" && pwd)/$(basename "$vrt_output")"
  export MULTISTATE_ANADEM_DEM
  echo "MULTISTATE_DEM_RESOLVED mode=vrt_mosaic tiles=${#candidates[@]} path=$MULTISTATE_ANADEM_DEM"
  printf 'MULTISTATE_DEM_TILE=%s\n' "${candidates[@]}"
}
