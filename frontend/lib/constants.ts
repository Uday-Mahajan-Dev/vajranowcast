/**
 * VajraNowcast Global Constants & Brand Tokens
 */

import { SeverityLevel } from "./types";

export const APP_NAME = "VajraNowcast";
export const APP_VERSION = "1.1.0";
export const APP_TAGLINE = "AI Thunderstorm & Lightning Nowcasting";
export const DEFAULT_DISCLAIMER = "Experimental AI nowcast product — not an official IMD weather warning.";

// Model Domain Geographic Bounds (6°–38°N, 68°–98°E)
export const COVERAGE_BOUNDS = {
  minLat: 6.0,
  maxLat: 38.0,
  minLon: 68.0,
  maxLon: 98.0,
};

export const OUTSIDE_COVERAGE_MESSAGE = "Outside the model's coverage area (6–38°N, 68–98°E)";

export const INITIAL_MAP_VIEW = {
  center: [78.9629, 22.5937] as [number, number], // Nagpur / Geographic Center of India
  zoom: 4.5,
  minZoom: 3.5,
  maxZoom: 14.0,
};

// 10 Major Indian Metros matching backend INDIAN_CITIES
export interface CityDef {
  name: string;
  lat: number;
  lon: number;
  state: string;
}

export const INDIAN_CITIES: CityDef[] = [
  { name: "Delhi", lat: 28.61, lon: 77.21, state: "Delhi NCR" },
  { name: "Mumbai", lat: 19.08, lon: 72.88, state: "Maharashtra" },
  { name: "Kolkata", lat: 22.57, lon: 88.36, state: "West Bengal" },
  { name: "Chennai", lat: 13.08, lon: 80.27, state: "Tamil Nadu" },
  { name: "Bengaluru", lat: 12.97, lon: 77.59, state: "Karnataka" },
  { name: "Hyderabad", lat: 17.39, lon: 78.49, state: "Telangana" },
  { name: "Jaipur", lat: 26.91, lon: 75.79, state: "Rajasthan" },
  { name: "Lucknow", lat: 26.85, lon: 80.95, state: "Uttar Pradesh" },
  { name: "Guwahati", lat: 26.14, lon: 91.74, state: "Assam" },
  { name: "Nagpur", lat: 21.15, lon: 79.09, state: "Maharashtra" },
];

// Statistical & Operational Thresholds
export const OPTIMAL_THRESHOLD = 0.186; // Statistical decision boundary
export const ALERT_THRESHOLD = 0.30;   // Operational watch threshold (minimum for public alert)
export const SEVERE_THRESHOLD = 0.60;  // Severe warning threshold

// 3 Operational Alert Tiers
export const ALERT_TIERS = {
  watch: {
    key: "watch",
    label: "Watch",
    minProb: 0.30,
    color: "#eab308", // yellow-500
    bgClass: "bg-yellow-500/15",
    borderClass: "border-yellow-500/30",
    textClass: "text-yellow-700 dark:text-yellow-400",
    badgeClass: "bg-yellow-500/20 text-yellow-800 dark:text-yellow-300 border-yellow-500/40",
    description: "Convective conditions developing: isolated showers/thunderstorms possible (≥ 30%).",
  },
  advisory: {
    key: "advisory",
    label: "Advisory",
    minProb: 0.40,
    color: "#f97316", // orange-500
    bgClass: "bg-orange-500/15",
    borderClass: "border-orange-500/30",
    textClass: "text-orange-700 dark:text-orange-400",
    badgeClass: "bg-orange-500/20 text-orange-800 dark:text-orange-300 border-orange-500/40",
    description: "Heavy rain / localized downpours likely in the next hour (≥ 40%).",
  },
  warning: {
    key: "warning",
    label: "Warning",
    minProb: 0.60,
    color: "#ef4444", // red-500
    bgClass: "bg-red-500/15",
    borderClass: "border-red-500/30",
    textClass: "text-red-700 dark:text-red-400",
    badgeClass: "bg-red-500/20 text-red-800 dark:text-red-300 border-red-500/40",
    description: "High-confidence severe thunderstorm & heavy rain expected (≥ 60%).",
  },
} as const;

export function getAlertTierFromProbability(prob: number): "warning" | "advisory" | "watch" | null {
  if (prob >= ALERT_TIERS.warning.minProb) return "warning";
  if (prob >= ALERT_TIERS.advisory.minProb) return "advisory";
  if (prob >= ALERT_TIERS.watch.minProb) return "watch";
  return null;
}

// Severity Scale Definitions (with text labels and color codes)
export interface SeverityMeta {
  level: SeverityLevel;
  label: string;
  shortLabel: string;
  minProb: number;
  maxProb: number;
  color: string;
  bgClass: string;
  borderClass: string;
  textClass: string;
  badgeClass: string;
  chipClass: string;
  description: string;
}

export const SEVERITY_CONFIG: Record<SeverityLevel, SeverityMeta> = {
  none: {
    level: "none",
    label: "None — low risk",
    shortLabel: "None",
    minProb: 0.0,
    maxProb: 0.186,
    color: "#64748b", // slate-500
    bgClass: "bg-slate-500/15",
    borderClass: "border-slate-500/30",
    textClass: "text-slate-400 dark:text-slate-300",
    badgeClass: "bg-slate-500/20 text-slate-300 border-slate-500/40",
    chipClass: "bg-slate-600/20 text-slate-300 border-slate-500/30",
    description: "Convective rain & thunderstorm probability is below operational threshold (< 18.6%).",
  },
  weak: {
    level: "weak",
    label: "Weak",
    shortLabel: "Weak",
    minProb: 0.186,
    maxProb: 0.40,
    color: "#eab308", // yellow-500
    bgClass: "bg-yellow-500/15",
    borderClass: "border-yellow-500/30",
    textClass: "text-yellow-600 dark:text-yellow-400",
    badgeClass: "bg-yellow-500/20 text-yellow-300 border-yellow-500/40",
    chipClass: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    description: "Elevated convective moisture and surface heating; isolated showers possible (18.6–40%).",
  },
  moderate: {
    level: "moderate",
    label: "Moderate",
    shortLabel: "Moderate",
    minProb: 0.40,
    maxProb: 0.60,
    color: "#f97316", // orange-500
    bgClass: "bg-orange-500/15",
    borderClass: "border-orange-500/30",
    textClass: "text-orange-600 dark:text-orange-400",
    badgeClass: "bg-orange-500/20 text-orange-300 border-orange-500/40",
    chipClass: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    description: "Moderate thunderstorm risk with gusty winds and sudden downpours likely (40–60%).",
  },
  severe: {
    level: "severe",
    label: "Severe",
    shortLabel: "Severe",
    minProb: 0.60,
    maxProb: 0.75,
    color: "#ef4444", // red-500
    bgClass: "bg-red-500/15",
    borderClass: "border-red-500/30",
    textClass: "text-red-600 dark:text-red-400",
    badgeClass: "bg-red-500/20 text-red-300 border-red-500/40",
    chipClass: "bg-red-500/20 text-red-400 border-red-500/30",
    description: "High confidence severe convective storm with frequent lightning and squalls (60–75%).",
  },
  very_severe: {
    level: "very_severe",
    label: "Very severe",
    shortLabel: "Very severe",
    minProb: 0.75,
    maxProb: 1.0,
    color: "#a855f7", // purple-500
    bgClass: "bg-purple-500/15",
    borderClass: "border-purple-500/30",
    textClass: "text-purple-600 dark:text-purple-400",
    badgeClass: "bg-purple-500/20 text-purple-300 border-purple-500/40",
    chipClass: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    description: "Dangerous deep convection, intense lightning strikes, heavy rain & severe squalls (≥ 75%).",
  },
};

export function getSeverityFromProbability(prob: number): SeverityMeta {
  if (prob >= 0.75) return SEVERITY_CONFIG.very_severe;
  if (prob >= 0.60) return SEVERITY_CONFIG.severe;
  if (prob >= 0.40) return SEVERITY_CONFIG.moderate;
  if (prob >= 0.186) return SEVERITY_CONFIG.weak;
  return SEVERITY_CONFIG.none;
}

// Map Style IDs and Metadata
export type MapStyleId = "default" | "dark" | "satellite";

export interface MapStyleConfig {
  id: MapStyleId;
  name: string;
  description: string;
  styleUrl: string;
  previewColor: string;
  themePreference: "light" | "dark";
}

/**
 * EOX Sentinel-2 Cloudless Imagery License & Verification:
 * Verified live: https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg (HTTP 200)
 * License terms: https://s2maps.eu / https://cloudless.eox.at
 * - 2020 Sentinel-2 Cloudless Layer: Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0)
 * - Required Attribution: "Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2020)"
 */
export const EOX_SATELLITE_WMTS_URL = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2020_3857/default/g/{z}/{y}/{x}.jpg";
export const EOX_ATTRIBUTION = "Sentinel-2 cloudless by EOX IT Services GmbH (Copernicus Sentinel 2020, CC BY-NC-SA 4.0)";

export const MAP_STYLES: Record<MapStyleId, MapStyleConfig> = {
  default: {
    id: "default",
    name: "Default (Light)",
    description: "Clean OpenFreeMap Liberty vector style with detailed roads and boundaries",
    styleUrl: "https://tiles.openfreemap.org/styles/liberty",
    previewColor: "#f1f5f9",
    themePreference: "light",
  },
  dark: {
    id: "dark",
    name: "Dark Canvas",
    description: "High-contrast dark vector map optimized for convective storm visualization",
    styleUrl: "https://tiles.openfreemap.org/styles/dark",
    previewColor: "#0f172a",
    themePreference: "dark",
  },
  satellite: {
    id: "satellite",
    name: "Hybrid Satellite",
    description: "EOX Sentinel-2 cloudless satellite imagery with vector roads & place labels",
    styleUrl: "satellite-hybrid", // Handled dynamically in map component
    previewColor: "#1e293b",
    themePreference: "light",
  },
};

// Open-Meteo Geocoding URL with verified countryCode=IN parameter
export const GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search";

// Full Map Attributions
export const MAP_ATTRIBUTIONS = [
  "© OpenStreetMap contributors",
  "OpenFreeMap",
  "EOX Sentinel-2 cloudless (s2maps.eu, CC BY-NC-SA 4.0)",
  "Place names: GeoNames (CC BY 4.0)",
  "Weather data: Open-Meteo (CC BY 4.0)",
  "Model: VajraNowcast v1.1.0",
];
