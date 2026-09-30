/**
 * Reverse Location Lookup Helper
 * Resolves clicked GPS coordinates to a friendly place name:
 * 1. Checks 10 monitored metro hubs within 25 km radius.
 * 2. Checks lazily loaded GeoNames India dataset (places_in.json).
 * 3. Falls back to coordinate format.
 */

import { INDIAN_CITIES } from "./constants";
import { calculateDistanceKm } from "./utils";
import { loadIndiaPlaces, CompactPlace } from "./places";

export async function lookupPlaceName(lat: number, lon: number): Promise<string> {
  // 1. Check if clicked point is within 25 km of one of our 10 major city hubs
  let closestHub = null;
  let minHubDistance = Infinity;

  for (const city of INDIAN_CITIES) {
    const dist = calculateDistanceKm(lat, lon, city.lat, city.lon);
    if (dist < minHubDistance) {
      minHubDistance = dist;
      closestHub = city;
    }
  }

  if (closestHub && minHubDistance <= 25) {
    return minHubDistance < 5 ? closestHub.name : `Near ${closestHub.name}, ${closestHub.state}`;
  }

  // 2. Check lazily loaded GeoNames India dataset
  try {
    const places = await loadIndiaPlaces();
    let closestPlace: CompactPlace | null = null;
    let minPlaceDistance = Infinity;

    for (let i = 0; i < places.length; i++) {
      const place = places[i];
      // Fast bbox rejection (~0.4° ≈ 44 km)
      if (Math.abs(lat - place.lt) > 0.45 || Math.abs(lon - place.ln) > 0.45) {
        continue;
      }
      const dist = calculateDistanceKm(lat, lon, place.lt, place.ln);
      if (dist < minPlaceDistance) {
        minPlaceDistance = dist;
        closestPlace = place;
      }
    }

    if (closestPlace && minPlaceDistance <= 35) {
      return minPlaceDistance < 4
        ? `${closestPlace.n}, ${closestPlace.s}`
        : `Near ${closestPlace.n}, ${closestPlace.s}`;
    }
  } catch (err) {
    console.warn("Reverse lookup error:", err);
  }

  // 3. Coordinate fallback
  return `${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`;
}
