import { NowcastResponse } from "./types";

interface CacheEntry {
  data: NowcastResponse;
  timestamp: number;
}

const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const nowcastCache = new Map<string, CacheEntry>();

/**
 * Snap coordinates to 0.25-degree spatial grid for deduplication
 */
export function getSpatialCacheKey(lat: number, lon: number): string {
  const snapLat = Math.round(lat / 0.25) * 0.25;
  const snapLon = Math.round(lon / 0.25) * 0.25;
  return `${snapLat.toFixed(2)}_${snapLon.toFixed(2)}`;
}

export function getCachedNowcast(lat: number, lon: number): NowcastResponse | null {
  const key = getSpatialCacheKey(lat, lon);
  const entry = nowcastCache.get(key);
  if (!entry) return null;

  const now = Date.now();
  if (now - entry.timestamp > CACHE_TTL_MS) {
    nowcastCache.delete(key);
    return null;
  }

  return entry.data;
}

export function setCachedNowcast(lat: number, lon: number, data: NowcastResponse): void {
  const key = getSpatialCacheKey(lat, lon);
  nowcastCache.set(key, {
    data,
    timestamp: Date.now(),
  });
}
