/**
 * Storm Impact Zone & Risk Surface Contour Generator for Replay & Live Mode
 * Converts a 5x5 meteorological local field into GeoJSON MultiPolygons using d3-contour,
 * generates the pulsing Watch-tier storm impact zone outline, rainfall cells, and 700 hPa storm track vector.
 */

import { contours } from "d3-contour";
import { LocalField, LocalFieldCell } from "./types";
import { ALERT_TIERS } from "./constants";

export interface ContourLayerData {
  riskContours: GeoJSON.FeatureCollection;
  impactZoneOutline: GeoJSON.FeatureCollection;
  rainCells: GeoJSON.FeatureCollection;
  stormTrack: GeoJSON.FeatureCollection;
  hasImpactZone: boolean;
  hasRain: boolean;
  hasTrack: boolean;
}

const SEVERITY_CONTOUR_METAS: Record<number, { label: string; color: string; fillOpacity: number; strokeColor: string }> = {
  0.186: { label: "Weak Risk", color: "#0d9488", fillOpacity: 0.25, strokeColor: "#14b8a6" },
  0.30:  { label: "Watch Impact Zone", color: "#eab308", fillOpacity: 0.35, strokeColor: "#facc15" },
  0.40:  { label: "Advisory", color: "#f97316", fillOpacity: 0.45, strokeColor: "#fb923c" },
  0.60:  { label: "Severe", color: "#ef4444", fillOpacity: 0.55, strokeColor: "#f87171" },
  0.75:  { label: "Very Severe", color: "#9333ea", fillOpacity: 0.65, strokeColor: "#c084fc" },
};

const CONTOUR_THRESHOLDS = [0.186, 0.30, 0.40, 0.60, 0.75];

/**
 * Bilinearly interpolates a 5x5 grid of numbers to an NxN resolution grid for smooth contour rendering.
 */
function interpolateGrid(grid5x5: number[][], N = 25): number[] {
  const result = new Array(N * N);
  const srcSize = 5;

  for (let r = 0; r < N; r++) {
    const v = (r / (N - 1)) * (srcSize - 1);
    const r0 = Math.floor(v);
    const r1 = Math.min(r0 + 1, srcSize - 1);
    const dr = v - r0;

    for (let c = 0; c < N; c++) {
      const u = (c / (N - 1)) * (srcSize - 1);
      const c0 = Math.floor(u);
      const c1 = Math.min(c0 + 1, srcSize - 1);
      const dc = u - c0;

      const v00 = grid5x5[r0][c0];
      const v01 = grid5x5[r0][c1];
      const v10 = grid5x5[r1][c0];
      const v11 = grid5x5[r1][c1];

      const top = v00 * (1 - dc) + v01 * dc;
      const bottom = v10 * (1 - dc) + v11 * dc;
      result[r * N + c] = top * (1 - dr) + bottom * dr;
    }
  }

  return result;
}

export function generateLocalFieldGeoJson(field?: LocalField | null): ContourLayerData {
  const emptyFC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

  if (!field || !field.cells || field.cells.length < 25) {
    return {
      riskContours: emptyFC,
      impactZoneOutline: emptyFC,
      rainCells: emptyFC,
      stormTrack: emptyFC,
      hasImpactZone: false,
      hasRain: false,
      hasTrack: false,
    };
  }

  const lats = [...field.lats].sort((a, b) => a - b); // Ascending: [minLat ... maxLat]
  const lons = [...field.lons].sort((a, b) => a - b); // Ascending: [minLon ... maxLon]

  const minLat = lats[0];
  const maxLat = lats[lats.length - 1];
  const minLon = lons[0];
  const maxLon = lons[lons.length - 1];

  // Organize 5x5 grid in row-major (top latitude to bottom latitude, left longitude to right longitude)
  // Row 0 = maxLat (north), Row 4 = minLat (south)
  const grid5x5: number[][] = Array.from({ length: 5 }, () => new Array(5).fill(0));
  const precip5x5: number[][] = Array.from({ length: 5 }, () => new Array(5).fill(0));

  field.cells.forEach((cell) => {
    // Find closest col (lon)
    let bestCol = 0;
    let minLonDist = Infinity;
    lons.forEach((l, idx) => {
      const d = Math.abs(l - cell.lon);
      if (d < minLonDist) {
        minLonDist = d;
        bestCol = idx;
      }
    });

    // Find closest row (lat: index 0 is maxLat, index 4 is minLat)
    let bestRow = 0;
    let minLatDist = Infinity;
    lats.forEach((l, idx) => {
      const d = Math.abs(l - cell.lat);
      if (d < minLatDist) {
        minLatDist = d;
        // Invert row index so row 0 is top (North / maxLat)
        bestRow = 4 - idx;
      }
    });

    grid5x5[bestRow][bestCol] = cell.prob;
    precip5x5[bestRow][bestCol] = cell.precipitation;
  });

  // 1. Generate smooth contours with d3-contour on an upsampled 25x25 grid
  const N = 25;
  const interpolatedVals = interpolateGrid(grid5x5, N);

  const contourGenerator = contours()
    .size([N, N])
    .thresholds(CONTOUR_THRESHOLDS);

  const rawContours = contourGenerator(interpolatedVals);

  // Transform pixel space [0..N, 0..N] to geographic [longitude, latitude]
  const contourFeatures: GeoJSON.Feature[] = [];
  const impactZoneFeatures: GeoJSON.Feature[] = [];

  rawContours.forEach((c) => {
    const thresh = c.value;
    const meta = SEVERITY_CONTOUR_METAS[thresh] || {
      label: `Risk ≥ ${(thresh * 100).toFixed(0)}%`,
      color: "#0d9488",
      fillOpacity: 0.3,
      strokeColor: "#14b8a6",
    };

    const transformedCoords = c.coordinates.map((polygon) =>
      polygon.map((ring) =>
        ring.map(([x, y]) => {
          const lon = minLon + (x / (N - 1)) * (maxLon - minLon);
          const lat = maxLat - (y / (N - 1)) * (maxLat - minLat);
          return [lon, lat];
        })
      )
    );

    if (transformedCoords.length > 0 && transformedCoords[0].length > 0) {
      const feature: GeoJSON.Feature = {
        type: "Feature",
        properties: {
          threshold: thresh,
          label: meta.label,
          color: meta.color,
          fill_opacity: meta.fillOpacity,
          stroke_color: meta.strokeColor,
        },
        geometry: {
          type: "MultiPolygon",
          coordinates: transformedCoords,
        },
      };

      contourFeatures.push(feature);

      // Threshold 0.30 is our official operational Watch-tier Storm Impact Zone boundary
      if (thresh === 0.30) {
        impactZoneFeatures.push({
          ...feature,
          properties: {
            ...feature.properties,
            is_impact_zone: true,
            title: "Storm Impact Zone (≥ 30% Watch)",
          },
        });
      }
    }
  });

  // 2. Generate Rain Cells GeoJSON (where precipitation >= 2.0 mm/h)
  const rainFeatures: GeoJSON.Feature[] = [];
  const cellHalfDeg = 0.125;

  field.cells.forEach((cell, idx) => {
    if (cell.precipitation >= 2.0) {
      const w = cell.lon - cellHalfDeg;
      const e = cell.lon + cellHalfDeg;
      const s = cell.lat - cellHalfDeg;
      const n = cell.lat + cellHalfDeg;

      rainFeatures.push({
        type: "Feature",
        id: `rain-${idx}`,
        properties: {
          precipitation: cell.precipitation,
          label: `${cell.precipitation.toFixed(1)} mm/h rain`,
        },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [w, s],
              [e, s],
              [e, n],
              [w, n],
              [w, s],
            ],
          ],
        },
      });
    }
  });

  // 3. Generate 700 hPa Wind Storm Track Vector
  const trackFeatures: GeoJSON.Feature[] = [];
  let hasTrack = false;

  if (field.wind_700hpa && field.wind_700hpa.speed_kmh > 0) {
    hasTrack = true;
    const centerLat = field.center_lat;
    const centerLon = field.center_lon;
    const speed = field.wind_700hpa.speed_kmh;
    const dirDeg = field.wind_700hpa.direction_deg;

    // Wind direction is the source; track moves in opposite direction (dirDeg + 180)
    const blowHeadingRad = ((dirDeg + 180) % 360) * (Math.PI / 180);

    // Scale track length for 1-hour advection distance (km to degrees)
    const trackDistKm = Math.max(15, Math.min(speed * 1.0, 55));
    const dLat = (trackDistKm / 111.32) * Math.cos(blowHeadingRad);
    const dLon = (trackDistKm / (111.32 * Math.cos(centerLat * (Math.PI / 180)))) * Math.sin(blowHeadingRad);

    const endLon = centerLon + dLon;
    const endLat = centerLat + dLat;

    // Line feature
    trackFeatures.push({
      type: "Feature",
      id: "storm-track-line",
      properties: {
        speed_kmh: speed,
        direction_deg: dirDeg,
        label: "Estimated storm track (from mid-level winds)",
      },
      geometry: {
        type: "LineString",
        coordinates: [
          [centerLon, centerLat],
          [endLon, endLat],
        ],
      },
    });

    // Arrowhead pointer polygon
    const headLenKm = 6.0;
    const headAngle = Math.PI / 6; // 30 deg
    const headLeftRad = blowHeadingRad + Math.PI - headAngle;
    const headRightRad = blowHeadingRad + Math.PI + headAngle;

    const headLeftLon = endLon + (headLenKm / (111.32 * Math.cos(endLat * (Math.PI / 180)))) * Math.sin(headLeftRad);
    const headLeftLat = endLat + (headLenKm / 111.32) * Math.cos(headLeftRad);

    const headRightLon = endLon + (headLenKm / (111.32 * Math.cos(endLat * (Math.PI / 180)))) * Math.sin(headRightRad);
    const headRightLat = endLat + (headLenKm / 111.32) * Math.cos(headRightRad);

    trackFeatures.push({
      type: "Feature",
      id: "storm-track-head",
      properties: {
        label: "Track Vector Head",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [endLon, endLat],
            [headLeftLon, headLeftLat],
            [headRightLon, headRightLat],
            [endLon, endLat],
          ],
        ],
      },
    });

    // Label point feature at midpoint
    trackFeatures.push({
      type: "Feature",
      id: "storm-track-label",
      properties: {
        title: "Estimated storm track (from mid-level winds)",
        speed_text: `${speed.toFixed(0)} km/h`,
      },
      geometry: {
        type: "Point",
        coordinates: [(centerLon + endLon) / 2, (centerLat + endLat) / 2],
      },
    });
  }

  return {
    riskContours: { type: "FeatureCollection", features: contourFeatures },
    impactZoneOutline: { type: "FeatureCollection", features: impactZoneFeatures },
    rainCells: { type: "FeatureCollection", features: rainFeatures },
    stormTrack: { type: "FeatureCollection", features: trackFeatures },
    hasImpactZone: impactZoneFeatures.length > 0,
    hasRain: rainFeatures.length > 0,
    hasTrack: trackFeatures.length > 0,
  };
}
