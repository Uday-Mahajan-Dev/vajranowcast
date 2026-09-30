/**
 * Model Domain Geographic Coverage Validation
 * Enforces atmospheric model boundary limits: Latitude 6.0°–38.0°N, Longitude 68.0°–98.0°E.
 * Note: Does not render political boundaries.
 */

import { COVERAGE_BOUNDS } from "./constants";

export function isWithinCoverageArea(lat: number, lon: number): boolean {
  return (
    lat >= COVERAGE_BOUNDS.minLat &&
    lat <= COVERAGE_BOUNDS.maxLat &&
    lon >= COVERAGE_BOUNDS.minLon &&
    lon <= COVERAGE_BOUNDS.maxLon
  );
}
