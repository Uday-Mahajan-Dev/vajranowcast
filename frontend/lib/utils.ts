import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format probability values: values < 0.01 (1%) display as "<1%", never "0%".
 */
export function formatProbability(prob?: number | null): string {
  if (prob === undefined || prob === null || isNaN(prob)) return "--%";
  if (prob < 0.01) return "<1%";
  return `${Math.round(prob * 100)}%`;
}

/**
 * Haversine formula to compute great-circle distance between two GPS coordinates in kilometers.
 */
export function calculateDistanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371; // Earth's radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Format any ISO timestamp into Indian Standard Time (IST, UTC+05:30)
 */
export function formatISTTime(dateStrOrObj?: string | Date | null, formatType: "short" | "full" | "timeOnly" | "window" = "short"): string {
  if (!dateStrOrObj) return "--:-- IST";
  const d = typeof dateStrOrObj === "string" ? new Date(dateStrOrObj) : dateStrOrObj;
  if (isNaN(d.getTime())) return "--:-- IST";

  const options: Intl.DateTimeFormatOptions = {
    timeZone: "Asia/Kolkata",
    hour12: false,
  };

  if (formatType === "timeOnly") {
    return (
      new Intl.DateTimeFormat("en-IN", {
        ...options,
        hour: "2-digit",
        minute: "2-digit",
      }).format(d) + " IST"
    );
  }

  if (formatType === "short") {
    return (
      new Intl.DateTimeFormat("en-IN", {
        ...options,
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(d) + " IST"
    );
  }

  return (
    new Intl.DateTimeFormat("en-IN", {
      ...options,
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d) + " IST"
  );
}

/**
 * Format a 1-hour prediction validity window (e.g. "14:00 – 15:00 IST")
 */
export function formatValidityWindow(fromStr?: string | null, untilStr?: string | null): string {
  if (!fromStr || !untilStr) return "Next 1 Hour";
  const f = new Date(fromStr);
  const u = new Date(untilStr);
  if (isNaN(f.getTime()) || isNaN(u.getTime())) return "Next 1 Hour";

  const fTime = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  }).format(f);

  const uTime = new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  }).format(u);

  return `${fTime} – ${uTime} IST`;
}

/**
 * Client-side Heat Index / Feels Like calculation (Rothfusz equation)
 * Labeled explicitly as calculated.
 */
export function calculateFeelsLike(tempC: number, rhPct: number): number {
  if (tempC < 20 || rhPct < 40) return tempC;
  const T = (tempC * 9) / 5 + 32; // Fahrenheit
  const R = rhPct;

  // Simple Rothfusz approximation
  const HI_F =
    -42.379 +
    2.04901523 * T +
    10.14333127 * R -
    0.22475541 * T * R -
    0.00683783 * T * T -
    0.05481717 * R * R +
    0.00122874 * T * T * R +
    0.00085282 * T * R * R -
    0.00000199 * T * T * R * R;

  const feelsC = ((HI_F - 32) * 5) / 9;
  return Math.round(feelsC * 10) / 10;
}

/**
 * WMO Weather Code lookup and descriptive label
 */
export interface WeatherCodeInfo {
  label: string;
  category: "clear" | "clouds" | "fog" | "drizzle" | "rain" | "snow" | "thunderstorm";
  iconName: string;
}

export function getWeatherCodeInfo(code?: number | null): WeatherCodeInfo {
  if (code === undefined || code === null) {
    return { label: "Fair / Variable", category: "clear", iconName: "Sun" };
  }

  switch (code) {
    case 0:
      return { label: "Clear sky", category: "clear", iconName: "Sun" };
    case 1:
      return { label: "Mainly clear", category: "clear", iconName: "SunDim" };
    case 2:
      return { label: "Partly cloudy", category: "clouds", iconName: "CloudSun" };
    case 3:
      return { label: "Overcast", category: "clouds", iconName: "Cloud" };
    case 45:
    case 48:
      return { label: "Fog / Depositing rime fog", category: "fog", iconName: "CloudFog" };
    case 51:
    case 53:
    case 55:
      return { label: "Drizzle (light to dense)", category: "drizzle", iconName: "CloudDrizzle" };
    case 61:
      return { label: "Slight rain", category: "rain", iconName: "CloudRain" };
    case 63:
      return { label: "Moderate rain", category: "rain", iconName: "CloudRain" };
    case 65:
      return { label: "Heavy rain", category: "rain", iconName: "CloudRainWind" };
    case 80:
    case 81:
    case 82:
      return { label: "Violent convective rain showers", category: "rain", iconName: "CloudRainWind" };
    case 95:
      return { label: "Thunderstorm (slight or moderate)", category: "thunderstorm", iconName: "CloudLightning" };
    case 96:
    case 99:
      return { label: "Severe thunderstorm with hail", category: "thunderstorm", iconName: "Zap" };
    default:
      return { label: `Weather Code ${code}`, category: "clouds", iconName: "Cloud" };
  }
}
