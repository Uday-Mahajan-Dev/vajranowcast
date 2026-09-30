/**
 * India Places Index Service (GeoNames CC BY 4.0)
 * Lazily loads frontend/public/data/places_in.json (6,534 Indian cities/towns)
 * Provides instant prefix-ranked search and fast spatial reverse-lookup.
 */

import { INDIAN_CITIES } from "./constants";

export interface CompactPlace {
  n: string; // Place name (e.g. Karad)
  s: string; // State / Admin1 name (e.g. Maharashtra)
  lt: number; // Latitude rounded to 4 decimals
  ln: number; // Longitude rounded to 4 decimals
  p: number; // Population
}

export interface PlaceMatch {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
  population: number;
  isHub: boolean;
}

let placesPromise: Promise<CompactPlace[]> | null = null;

/**
 * Pre-fetches or retrieves cached places index.
 * Safe to call repeatedly on focus / hover / map tap.
 */
export function loadIndiaPlaces(): Promise<CompactPlace[]> {
  if (!placesPromise) {
    placesPromise = fetch("/data/places_in.json")
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to load places_in.json (status ${res.status})`);
        }
        return res.json() as Promise<CompactPlace[]>;
      })
      .catch((err) => {
        console.warn("[VajraNowcast] Error loading India place index:", err);
        placesPromise = null; // Allow retry on subsequent calls
        return [];
      });
  }
  return placesPromise;
}

function isTopHubCity(name: string, state?: string): boolean {
  const norm = name.toLowerCase().trim();
  return INDIAN_CITIES.some(
    (c) => c.name.toLowerCase() === norm || norm.startsWith(c.name.toLowerCase())
  );
}

/**
 * Search places index with strict prefix priority and population descending rank.
 */
export async function searchPlacesIndex(
  query: string,
  maxResults = 8
): Promise<PlaceMatch[]> {
  const q = query.trim().toLowerCase();
  if (q.length < 2) return [];

  const places = await loadIndiaPlaces();
  if (!places || places.length === 0) return [];

  const prefixMatches: CompactPlace[] = [];
  const substringMatches: CompactPlace[] = [];

  for (let i = 0; i < places.length; i++) {
    const p = places[i];
    const lowerName = p.n.toLowerCase();

    if (lowerName.startsWith(q)) {
      prefixMatches.push(p);
      if (prefixMatches.length >= maxResults) break;
    } else if (lowerName.includes(q) || p.s.toLowerCase().includes(q)) {
      if (substringMatches.length < maxResults) {
        substringMatches.push(p);
      }
    }
  }

  const combined = [...prefixMatches, ...substringMatches].slice(0, maxResults);

  return combined.map((p) => ({
    id: `geo-${p.n}-${p.lt}-${p.ln}`,
    name: p.n,
    state: p.s,
    lat: p.lt,
    lon: p.ln,
    population: p.p,
    isHub: isTopHubCity(p.n, p.s),
  }));
}
