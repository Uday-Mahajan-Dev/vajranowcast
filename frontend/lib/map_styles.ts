/**
 * Map Style Compositor for MapLibre GL JS
 * Builds Light, Dark, and Hybrid Satellite styles with country boundary filters
 * and high-contrast labeling.
 */

import { EOX_SATELLITE_WMTS_URL } from "./constants";
import type { StyleSpecification } from "maplibre-gl";

// Cache for raw fetched style JSONs
let cachedLibertyStyle: StyleSpecification | null = null;
let cachedDarkStyle: StyleSpecification | null = null;

/**
 * Fetch and cache raw OpenFreeMap Liberty style JSON
 */
export async function getRawLibertyStyle(): Promise<StyleSpecification> {
  if (cachedLibertyStyle) return JSON.parse(JSON.stringify(cachedLibertyStyle));
  const res = await fetch("https://tiles.openfreemap.org/styles/liberty");
  if (!res.ok) throw new Error("Failed to fetch OpenFreeMap liberty style");
  const data = (await res.json()) as StyleSpecification;
  cachedLibertyStyle = data;
  return JSON.parse(JSON.stringify(data));
}

/**
 * Fetch and cache raw OpenFreeMap Dark style JSON
 */
export async function getRawDarkStyle(): Promise<StyleSpecification> {
  if (cachedDarkStyle) return JSON.parse(JSON.stringify(cachedDarkStyle));
  const res = await fetch("https://tiles.openfreemap.org/styles/dark");
  if (!res.ok) throw new Error("Failed to fetch OpenFreeMap dark style");
  const data = (await res.json()) as StyleSpecification;
  cachedDarkStyle = data;
  return JSON.parse(JSON.stringify(data));
}

/**
 * Default Light Style: OpenFreeMap Liberty with country-level boundary lines hidden
 * (hides boundary_2 and boundary_disputed; keeps boundary_3 for state boundaries).
 */
export async function buildDefaultLightStyle(): Promise<StyleSpecification> {
  const style = await getRawLibertyStyle();
  style.name = "VajraNowcast Default Light";

  // Hide country-level boundaries (admin_level 2 and disputed lines)
  style.layers = (style.layers || []).filter((layer) => {
    if (layer.id === "boundary_2" || layer.id === "boundary_disputed") {
      return false;
    }
    return true;
  });

  return style;
}

/**
 * Enhanced Dark Style: OpenFreeMap Dark with enhanced text halos, road contrast,
 * and country-level boundary lines hidden (hides boundary_country_z0-4 and boundary_country_z5-; keeps boundary_state).
 */
export async function buildEnhancedDarkStyle(): Promise<StyleSpecification> {
  const style = await getRawDarkStyle();
  style.name = "VajraNowcast Dark Canvas";

  style.layers = (style.layers || [])
    .filter((layer) => {
      // Hide country boundary lines
      if (layer.id === "boundary_country_z0-4" || layer.id === "boundary_country_z5-") {
        return false;
      }
      return true;
    })
    .map((layer) => {
      const l = { ...layer };
      // Enhance symbol readability
      if (l.type === "symbol" && l.layout && l.layout["text-field"]) {
        l.paint = {
          ...(l.paint || {}),
          "text-color": "#f8fafc",
          "text-halo-color": "#090d16",
          "text-halo-width": 1.6,
          "text-halo-blur": 0.4,
        };
      }
      return l;
    });

  return style;
}

/**
 * Hybrid Satellite Style:
 * Base: EOX Sentinel-2 2020 cloudless raster WMTS
 * Overlays: Road, state-boundary (boundary_3), and label symbol layers from Liberty,
 * restyled with white text + dark halos.
 */
export async function buildSatelliteHybridStyle(): Promise<StyleSpecification> {
  const baseStyle = await getRawLibertyStyle();

  // Filter overlay layers: Keep only roads, waterways, state boundaries, and labels
  const overlayLayers = (baseStyle.layers || []).filter((layer) => {
    // Exclude background and polygon fills
    if (layer.type === "background") return false;
    if (layer.id.includes("landcover") || layer.id.includes("landuse") || layer.id.includes("park")) return false;
    if (layer.id.includes("water") && layer.type === "fill") return false;
    if (layer.id.includes("building") && layer.type === "fill") return false;

    // Exclude country-level boundaries
    if (layer.id === "boundary_2" || layer.id === "boundary_disputed") return false;

    return true;
  });

  // Restyle overlay layers for maximum legibility on satellite imagery
  const restyledLayers = overlayLayers.map((layer) => {
    const l = { ...layer };
    if (l.type === "symbol" && l.layout && l.layout["text-field"]) {
      l.paint = {
        ...(l.paint || {}),
        "text-color": "#ffffff",
        "text-halo-color": "#090d16",
        "text-halo-width": 1.8,
        "text-halo-blur": 0.5,
      };
    } else if (l.type === "line") {
      if (l.id === "boundary_3") {
        l.paint = {
          ...(l.paint || {}),
          "line-color": "#e2e8f0",
          "line-opacity": 0.75,
          "line-width": 1.4,
          "line-dasharray": [2, 2],
        };
      } else if (l.id.includes("road") || l.id.includes("highway") || l.id.includes("tunnel") || l.id.includes("bridge")) {
        l.paint = {
          ...(l.paint || {}),
          "line-opacity": 0.6,
        };
      }
    }
    return l;
  });

  // Add EOX Satellite Raster Source
  const sources = {
    ...(baseStyle.sources || {}),
    "eox-satellite": {
      type: "raster" as const,
      tiles: [EOX_SATELLITE_WMTS_URL],
      tileSize: 256,
      maxzoom: 14,
      attribution: "Sentinel-2 cloudless by EOX IT Services GmbH (CC BY-NC-SA 4.0)",
    },
  };

  const backgroundLayer = {
    id: "satellite-background",
    type: "background" as const,
    paint: {
      "background-color": "#090d16",
    },
  };

  const satelliteRasterLayer = {
    id: "eox-satellite-base",
    type: "raster" as const,
    source: "eox-satellite",
    minzoom: 0,
    maxzoom: 24,
    paint: {
      "raster-opacity": 1.0,
      "raster-fade-duration": 150,
    },
  };

  return {
    version: 8,
    name: "VajraNowcast Hybrid Satellite",
    glyphs: baseStyle.glyphs || "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
    sprite: baseStyle.sprite || "https://tiles.openfreemap.org/sprites/liberty",
    sources,
    layers: [backgroundLayer, satelliteRasterLayer, ...restyledLayers],
  };
}
