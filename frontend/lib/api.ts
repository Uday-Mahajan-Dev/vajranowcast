/**
 * VajraNowcast Typed API Client
 * Interfaces with FastAPI backend and handles cold-starts, abort signals, and caching.
 */

import {
  ActiveAlertsResponse,
  AlertResponse,
  CitiesNowcastResponse,
  DEFAULT_DISCLAIMER,
  GeocodingResult,
  GridResponse,
  HistoricalReplayEvent,
  HistoricalResponse,
  ModelInfo,
  NowcastResponse,
  DataSourceStatus,
} from "./types";
import { GEOCODING_API_URL, COVERAGE_BOUNDS } from "./constants";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const rawStaticBase = (process.env.NEXT_PUBLIC_STATIC_BASE_URL || "").trim();
const isStaticBaseValid =
  rawStaticBase.startsWith("http://") ||
  rawStaticBase.startsWith("https://") ||
  rawStaticBase.startsWith("/");
const STATIC_BASE_URL = isStaticBaseValid ? rawStaticBase.replace(/\/$/, "") : null;

let hasLoggedGridSource = false;

// In-memory cache for nowcast coordinates (0.25 deg cell key)
interface CacheEntry<T> {
  data: T;
  timestamp: number;
}
const nowcastMemoryCache = new Map<string, CacheEntry<NowcastResponse>>();
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes client-side cache

function snapCoord(val: number, step = 0.25): number {
  return Math.round(val / step) * step;
}

export class ApiError extends Error {
  statusCode: number;
  data?: any;

  constructor(message: string, statusCode: number, data?: any) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
    this.data = data;
  }
}

/**
 * Fetch helper with timeout and cold-start detection callback
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = 70000,
  onColdStart?: (isWaking: boolean) => void
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let coldStartTimer: NodeJS.Timeout | null = null;
  if (onColdStart) {
    coldStartTimer = setTimeout(() => {
      onColdStart(true);
    }, 4500); // Trigger cold-start alert after 4.5s
  }

  // Chain external signal if passed
  const externalSignal = options.signal;
  if (externalSignal) {
    externalSignal.addEventListener("abort", () => controller.abort());
  }

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    return res;
  } finally {
    clearTimeout(timer);
    if (coldStartTimer) clearTimeout(coldStartTimer);
    if (onColdStart) onColdStart(false);
  }
}

/**
 * Generic JSON handler with status code mapping
 */
async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorDetail = `Request failed with status ${res.status}`;
    try {
      const errJson = await res.json();
      if (errJson.detail) {
        if (typeof errJson.detail === "string") {
          errorDetail = errJson.detail;
        } else if (Array.isArray(errJson.detail)) {
          errorDetail = errJson.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ");
        }
      }
    } catch {
      // Non-json response
    }

    if (res.status === 422) {
      throw new ApiError(`Validation error: ${errorDetail}`, 422);
    } else if (res.status === 429) {
      throw new ApiError("Too many requests, try again in a minute.", 429);
    } else if (res.status === 401) {
      throw new ApiError("Unauthorized. Please log in.", 401);
    } else if (res.status === 403) {
      throw new ApiError("Access forbidden. Insufficient permissions.", 403);
    } else {
      throw new ApiError(errorDetail, res.status);
    }
  }
  return res.json() as Promise<T>;
}

// ----------------------------------------------------------------------
// Prediction Endpoints
// ----------------------------------------------------------------------

export async function fetchNowcast(
  lat: number,
  lon: number,
  leadHours: number[] = [0, 1, 2, 3, 6],
  signal?: AbortSignal,
  onColdStart?: (isWaking: boolean) => void
): Promise<NowcastResponse> {
  const snappedLat = snapCoord(lat);
  const snappedLon = snapCoord(lon);
  const cacheKey = `${snappedLat.toFixed(2)}_${snappedLon.toFixed(2)}_${leadHours.join(",")}`;

  const cached = nowcastMemoryCache.get(cacheKey);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
    return cached.data;
  }

  const queryParams = new URLSearchParams({
    lat: snappedLat.toString(),
    lon: snappedLon.toString(),
    lead_hours: leadHours.join(","),
  });

  const url = `${API_BASE_URL}/api/v1/predictions/nowcast?${queryParams.toString()}`;
  const res = await fetchWithTimeout(url, { signal }, 70000, onColdStart);
  const data = await handleResponse<NowcastResponse>(res);

  nowcastMemoryCache.set(cacheKey, { data, timestamp: Date.now() });
  return data;
}

export async function fetchCitiesNowcast(
  signal?: AbortSignal,
  onColdStart?: (isWaking: boolean) => void
): Promise<CitiesNowcastResponse> {
  const url = `${API_BASE_URL}/api/v1/predictions/nowcast/cities`;
  const res = await fetchWithTimeout(url, { signal }, 70000, onColdStart);
  return handleResponse<CitiesNowcastResponse>(res);
}

export async function fetchGrid(
  signal?: AbortSignal,
  onColdStart?: (isWaking: boolean) => void
): Promise<GridResponse> {
  // 1. Try static base URL if configured and valid
  if (STATIC_BASE_URL) {
    if (!hasLoggedGridSource) {
      console.info(`[VajraNowcast] Using static CDN grid source: ${STATIC_BASE_URL}/grid_latest.json`);
      hasLoggedGridSource = true;
    }
    try {
      const cdnUrl = `${STATIC_BASE_URL}/grid_latest.json`;
      const cdnRes = await fetchWithTimeout(cdnUrl, { signal }, 5000);
      if (cdnRes.ok) {
        return await cdnRes.json();
      }
    } catch {
      // Fall through to backend API
    }
  } else {
    if (!hasLoggedGridSource) {
      console.info(`[VajraNowcast] Static CDN base URL disabled/unset. Using backend API grid source: ${API_BASE_URL}/api/v1/predictions/grid`);
      hasLoggedGridSource = true;
    }
  }

  // 2. Fall back to backend /api/v1/predictions/grid
  const url = `${API_BASE_URL}/api/v1/predictions/grid`;
  const res = await fetchWithTimeout(url, { signal }, 70000, onColdStart);
  return handleResponse<GridResponse>(res);
}

export async function fetchHistoricalReplays(signal?: AbortSignal): Promise<HistoricalReplayEvent[]> {
  const url = `${API_BASE_URL}/api/v1/predictions/historical/replays`;
  const res = await fetchWithTimeout(url, { signal }, 15000);
  return handleResponse<HistoricalReplayEvent[]>(res);
}

export async function fetchHistoricalVerification(
  lat: number,
  lon: number,
  date: string,
  hour: number,
  eventId?: string,
  signal?: AbortSignal
): Promise<HistoricalResponse> {
  const params = new URLSearchParams({
    lat: lat.toString(),
    lon: lon.toString(),
    date,
    hour: hour.toString(),
  });
  if (eventId) {
    params.set("event_id", eventId);
  }

  const url = `${API_BASE_URL}/api/v1/predictions/historical?${params.toString()}`;
  const res = await fetchWithTimeout(url, { signal }, 30000);
  return handleResponse<HistoricalResponse>(res);
}

export async function fetchModelInfo(signal?: AbortSignal): Promise<ModelInfo> {
  const url = `${API_BASE_URL}/api/v1/predictions/model/info`;
  const res = await fetchWithTimeout(url, { signal }, 10000);
  return handleResponse<ModelInfo>(res);
}

// ----------------------------------------------------------------------
// Weather & Indices Endpoints
// ----------------------------------------------------------------------

export async function fetchCurrentWeather(lat: number, lon: number, signal?: AbortSignal): Promise<any> {
  const url = `${API_BASE_URL}/api/v1/weather/current?lat=${lat}&lon=${lon}`;
  const res = await fetchWithTimeout(url, { signal }, 20000);
  return handleResponse<any>(res);
}

export async function fetchAtmosphericIndices(lat: number, lon: number, signal?: AbortSignal): Promise<any> {
  const url = `${API_BASE_URL}/api/v1/weather/indices?lat=${lat}&lon=${lon}`;
  const res = await fetchWithTimeout(url, { signal }, 20000);
  return handleResponse<any>(res);
}

export async function fetchSourcesStatus(signal?: AbortSignal): Promise<DataSourceStatus[]> {
  const url = `${API_BASE_URL}/api/v1/weather/sources/status`;
  const res = await fetchWithTimeout(url, { signal }, 10000);
  return handleResponse<DataSourceStatus[]>(res);
}

// ----------------------------------------------------------------------
// Alert Endpoints
// ----------------------------------------------------------------------

export async function fetchActiveAlerts(signal?: AbortSignal): Promise<ActiveAlertsResponse> {
  const url = `${API_BASE_URL}/api/v1/alerts/active`;
  const res = await fetchWithTimeout(url, { signal }, 15000);
  return handleResponse<ActiveAlertsResponse>(res);
}

export async function generateAlerts(token: string): Promise<{
  timestamp: string;
  triggered_by: string;
  alerts_generated: number;
  alerts: AlertResponse[];
  disclaimer: string;
}> {
  const url = `${API_BASE_URL}/api/v1/alerts/generate`;
  const res = await fetchWithTimeout(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });
  return handleResponse(res);
}

export async function createTestAlert(
  tokenOrAdminKey: string,
  payload: { city: string; tier: string; lead_time_hours?: number }
): Promise<{
  timestamp: string;
  triggered_by: string;
  alert: AlertResponse;
  disclaimer: string;
}> {
  const url = `${API_BASE_URL}/api/v1/alerts/test`;
  const isBearer = tokenOrAdminKey.startsWith("ey") || tokenOrAdminKey.includes(".");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (isBearer) {
    headers["Authorization"] = `Bearer ${tokenOrAdminKey}`;
  } else {
    headers["X-Admin-Token"] = tokenOrAdminKey;
  }

  const res = await fetchWithTimeout(url, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

// ----------------------------------------------------------------------
// Open-Meteo Geocoding Client (Restricted to India)
// ----------------------------------------------------------------------

let lastGeocodeRequestTime = 0;

export async function searchIndianPlaces(query: string, signal?: AbortSignal): Promise<GeocodingResult[]> {
  const trimmed = query.trim();
  if (trimmed.length < 2) return [];

  // Enforce max 1 request/second rate-limit
  const now = Date.now();
  const timeSinceLast = now - lastGeocodeRequestTime;
  if (timeSinceLast < 1000) {
    await new Promise((r) => setTimeout(r, 1000 - timeSinceLast));
  }
  lastGeocodeRequestTime = Date.now();

  // Verified parameter: countryCode=IN ensures pure India search
  const url = `${GEOCODING_API_URL}?name=${encodeURIComponent(trimmed)}&count=6&language=en&format=json&countryCode=IN`;

  try {
    const res = await fetch(url, { signal });
    if (!res.ok) return [];
    const data = await res.json();
    const results: GeocodingResult[] = data.results || [];

    // Client-side safety filter to strict India coordinate bounding box
    return results.filter((place) => {
      return (
        place.latitude >= COVERAGE_BOUNDS.minLat &&
        place.latitude <= COVERAGE_BOUNDS.maxLat &&
        place.longitude >= COVERAGE_BOUNDS.minLon &&
        place.longitude <= COVERAGE_BOUNDS.maxLon
      );
    });
  } catch (e: any) {
    if (e.name === "AbortError") return [];
    console.warn("Geocoding search error:", e);
    return [];
  }
}
