"use client";

import React, { useEffect, useRef, memo, useCallback } from "react";
import maplibregl, { Map, Marker } from "maplibre-gl";
import { INITIAL_MAP_VIEW, MapStyleId, SEVERITY_CONFIG, INDIAN_CITIES } from "@/lib/constants";
import {
  buildDefaultLightStyle,
  buildEnhancedDarkStyle,
  buildSatelliteHybridStyle,
} from "@/lib/map_styles";
import { isWithinCoverageArea } from "@/lib/coverage_area";
import { MapLayerSettings } from "./MapTypeModal";
import {
  GridPointPrediction,
  CitiesNowcastResponse,
  AlertResponse,
  HistoricalReplayEvent,
  ReplayTimelineHour,
  SeverityLevel,
} from "@/lib/types";
import { formatProbability } from "@/lib/utils";
import { generateLocalFieldGeoJson } from "@/lib/contour_generator";
import { LeadTimeOption } from "./LeadTimeSlider";
import { Info, ShieldAlert } from "lucide-react";

export interface SelectedLocation {
  lat: number;
  lon: number;
  name?: string;
}

export interface UserLocation {
  lat: number;
  lon: number;
}

export interface FlyToTarget {
  lat: number;
  lon: number;
  zoom?: number;
}

interface MapLibreMapProps {
  mapStyle: MapStyleId;
  selectedLocation: SelectedLocation | null;
  userLocation: UserLocation | null;
  flyToTarget: FlyToTarget | null;
  layers: MapLayerSettings;
  gridPoints: GridPointPrediction[];
  citiesData: CitiesNowcastResponse | null;
  activeAlerts: AlertResponse[];
  selectedLead?: LeadTimeOption;
  activeReplay?: HistoricalReplayEvent | null;
  activeReplayHour?: ReplayTimelineHour | null;
  onMapClick: (loc: { lat: number; lon: number }) => void;
  onSelectCity: (cityName: string, lat: number, lon: number) => void;
  onOutsideClick: () => void;
  onBearingChange?: (bearing: number) => void;
  onMapLoaded?: (map: Map) => void;
  className?: string;
}

const MapLibreMapComponent: React.FC<MapLibreMapProps> = ({
  mapStyle,
  selectedLocation,
  userLocation,
  flyToTarget,
  layers,
  gridPoints,
  citiesData,
  activeAlerts,
  selectedLead = 0,
  activeReplay = null,
  activeReplayHour = null,
  onMapClick,
  onSelectCity,
  onOutsideClick,
  onBearingChange,
  onMapLoaded,
  className = "",
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);

  // Latest-ref pattern for callbacks and dynamic data
  const onMapClickRef = useRef(onMapClick);
  onMapClickRef.current = onMapClick;

  const onSelectCityRef = useRef(onSelectCity);
  onSelectCityRef.current = onSelectCity;

  const onOutsideClickRef = useRef(onOutsideClick);
  onOutsideClickRef.current = onOutsideClick;

  const onBearingChangeRef = useRef(onBearingChange);
  onBearingChangeRef.current = onBearingChange;

  const onMapLoadedRef = useRef(onMapLoaded);
  onMapLoadedRef.current = onMapLoaded;

  // Track applied style
  const currentAppliedStyleRef = useRef<MapStyleId | null>(null);

  // Marker storage
  const selectedMarkerRef = useRef<Marker | null>(null);
  const userMarkerRef = useRef<Marker | null>(null);
  const replayMarkerRef = useRef<Marker | null>(null);
  const cityMarkersRef = useRef<globalThis.Map<string, Marker>>(new globalThis.Map());

  // Convert grid points to GeoJSON FeatureCollection
  const buildGridGeoJson = useCallback((points: GridPointPrediction[]): GeoJSON.FeatureCollection => {
    return {
      type: "FeatureCollection",
      features: points.map((pt, idx) => ({
        type: "Feature",
        id: idx,
        properties: {
          latitude: pt.latitude,
          longitude: pt.longitude,
          thunderstorm_probability: pt.thunderstorm_probability,
          severity: pt.severity,
          prob_pct: formatProbability(pt.thunderstorm_probability),
          color: SEVERITY_CONFIG[pt.severity]?.color || "#64748b",
        },
        geometry: {
          type: "Point",
          coordinates: [pt.longitude, pt.latitude],
        },
      })),
    };
  }, []);

  // Attach or re-attach custom overlay sources & layers
  const syncOverlayLayers = useCallback(
    (map: Map, currentLayers: MapLayerSettings, points: GridPointPrediction[]) => {
      if (!map.isStyleLoaded()) return;

      const geojsonData = buildGridGeoJson(points);

      // 1. Grid Points & Heatmap Source
      const source = map.getSource("grid-points-source") as maplibregl.GeoJSONSource | undefined;
      if (!source) {
        map.addSource("grid-points-source", {
          type: "geojson",
          data: geojsonData,
        });
      } else {
        source.setData(geojsonData);
      }

      // 2. Risk Heatmap Layer (weight = thunderstorm_probability, fades out between zoom 5 and 7)
      if (!map.getLayer("grid-risk-heatmap")) {
        map.addLayer(
          {
            id: "grid-risk-heatmap",
            type: "heatmap",
            source: "grid-points-source",
            maxzoom: 9,
            layout: {
              visibility: currentLayers.showHeatmap ? "visible" : "none",
            },
            paint: {
              "heatmap-weight": ["get", "thunderstorm_probability"],
              "heatmap-intensity": [
                "interpolate",
                ["linear"],
                ["zoom"],
                3,
                0.6,
                6,
                1.4,
              ],
              "heatmap-color": [
                "interpolate",
                ["linear"],
                ["heatmap-density"],
                0,
                "rgba(100, 116, 139, 0)",
                0.186,
                "rgba(234, 179, 8, 0.65)",
                0.4,
                "rgba(249, 115, 22, 0.8)",
                0.6,
                "rgba(239, 68, 68, 0.9)",
                0.8,
                "rgba(168, 85, 247, 0.95)",
              ],
              "heatmap-radius": [
                "interpolate",
                ["linear"],
                ["zoom"],
                3,
                24,
                5,
                48,
                8,
                72,
              ],
              "heatmap-opacity": [
                "interpolate",
                ["linear"],
                ["zoom"],
                5,
                0.85,
                7,
                0.0,
              ],
            },
          },
          map.getStyle()?.layers?.find((l) => l.type === "symbol")?.id
        );
      } else {
        map.setLayoutProperty(
          "grid-risk-heatmap",
          "visibility",
          currentLayers.showHeatmap ? "visible" : "none"
        );
      }

      // 3. Grid Point Circles (fades in between zoom 5 and 7)
      if (!map.getLayer("grid-points-circles")) {
        map.addLayer({
          id: "grid-points-circles",
          type: "circle",
          source: "grid-points-source",
          layout: {
            visibility: currentLayers.showGridPoints ? "visible" : "none",
          },
          paint: {
            "circle-color": ["get", "color"],
            "circle-radius": [
              "interpolate",
              ["linear"],
              ["zoom"],
              3,
              3,
              6,
              6,
              8,
              10,
            ],
            "circle-stroke-width": 1.5,
            "circle-stroke-color": "#ffffff",
            "circle-opacity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              4.5,
              0.4,
              6.5,
              0.9,
              8,
              1.0,
            ],
            "circle-stroke-opacity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              4.5,
              0.5,
              6.5,
              1.0,
            ],
          },
        });

        // Click listener on grid point circles
        map.on("click", "grid-points-circles", (e) => {
          if (e.features && e.features[0]) {
            const geom = e.features[0].geometry as GeoJSON.Point;
            const [lon, lat] = geom.coordinates;
            if (onMapClickRef.current) {
              onMapClickRef.current({ lat, lon });
            }
          }
        });

        map.on("mouseenter", "grid-points-circles", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "grid-points-circles", () => {
          map.getCanvas().style.cursor = "";
        });
      } else {
        map.setLayoutProperty(
          "grid-points-circles",
          "visibility",
          currentLayers.showGridPoints ? "visible" : "none"
        );
      }

      // 4. Grid Point Labels (appears from zoom >= 6)
      if (!map.getLayer("grid-points-labels")) {
        map.addLayer({
          id: "grid-points-labels",
          type: "symbol",
          source: "grid-points-source",
          minzoom: 6.0,
          layout: {
            visibility: currentLayers.showGridPoints ? "visible" : "none",
            "text-field": ["get", "prob_pct"],
            "text-size": 11,
            "text-offset": [0, 1.2],
            "text-anchor": "top",
            "text-allow-overlap": false,
          },
          paint: {
            "text-color": "#ffffff",
            "text-halo-color": "#090d16",
            "text-halo-width": 1.6,
          },
        });
      } else {
        map.setLayoutProperty(
          "grid-points-labels",
          "visibility",
          currentLayers.showGridPoints ? "visible" : "none"
        );
      }

      // =======================================================================
      // 5. Historical Replay Risk Contours (P(TS) smooth surface)
      // =======================================================================
      if (!map.getSource("replay-contours-source")) {
        map.addSource("replay-contours-source", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        map.addLayer({
          id: "replay-contours-fill",
          type: "fill",
          source: "replay-contours-source",
          paint: {
            "fill-color": ["get", "color"],
            "fill-opacity": ["get", "fill_opacity"],
          },
        });

        map.addLayer({
          id: "replay-contours-line",
          type: "line",
          source: "replay-contours-source",
          paint: {
            "line-color": ["get", "stroke_color"],
            "line-width": 1.2,
            "line-opacity": 0.75,
          },
        });
      }

      // =======================================================================
      // 6. Historical Replay Storm Impact Zone Outline (P(TS) >= 0.30 Watch)
      // =======================================================================
      if (!map.getSource("replay-impact-zone-source")) {
        map.addSource("replay-impact-zone-source", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        map.addLayer({
          id: "replay-impact-zone-outline",
          type: "line",
          source: "replay-impact-zone-source",
          paint: {
            "line-color": "#eab308",
            "line-width": 2.6,
            "line-dasharray": [3, 2],
            "line-opacity": 0.95,
          },
        });
      }

      // =======================================================================
      // 7. Historical Replay Rain Cells Layer (precipitation >= 2.0 mm/h)
      // =======================================================================
      if (!map.getSource("replay-rain-source")) {
        map.addSource("replay-rain-source", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        map.addLayer({
          id: "replay-rain-cells-fill",
          type: "fill",
          source: "replay-rain-source",
          paint: {
            "fill-color": "#38bdf8",
            "fill-opacity": 0.25,
          },
        });

        map.addLayer({
          id: "replay-rain-cells-line",
          type: "line",
          source: "replay-rain-source",
          paint: {
            "line-color": "#0284c7",
            "line-width": 1.0,
            "line-dasharray": [1, 2],
          },
        });
      }

      // =======================================================================
      // 8. Historical Replay 700 hPa Steering Storm Track Vector
      // =======================================================================
      if (!map.getSource("replay-storm-track-source")) {
        map.addSource("replay-storm-track-source", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        map.addLayer({
          id: "replay-storm-track-line",
          type: "line",
          source: "replay-storm-track-source",
          filter: ["==", "$type", "LineString"],
          paint: {
            "line-color": "#38bdf8",
            "line-width": 3.0,
            "line-opacity": 0.95,
          },
        });

        map.addLayer({
          id: "replay-storm-track-head",
          type: "fill",
          source: "replay-storm-track-source",
          filter: ["==", "$type", "Polygon"],
          paint: {
            "fill-color": "#38bdf8",
            "fill-opacity": 1.0,
          },
        });

        map.addLayer({
          id: "replay-storm-track-label",
          type: "symbol",
          source: "replay-storm-track-source",
          filter: ["==", "$type", "Point"],
          layout: {
            "text-field": ["get", "title"],
            "text-size": 11,
            "text-offset": [0, -1.2],
            "text-anchor": "bottom",
            "text-allow-overlap": true,
          },
          paint: {
            "text-color": "#38bdf8",
            "text-halo-color": "#020617",
            "text-halo-width": 2.0,
          },
        });
      }
    },
    [buildGridGeoJson]
  );

  // 1. Initialize MapLibre instance exactly ONCE with persisted initial style
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    if (process.env.NODE_ENV !== "production") {
      console.log("[map] created");
    }

    let isDisposed = false;

    const initializeMap = async () => {
      let initialStyleObj: any = "https://tiles.openfreemap.org/styles/liberty";
      try {
        if (mapStyle === "satellite") {
          initialStyleObj = await buildSatelliteHybridStyle();
        } else if (mapStyle === "dark") {
          initialStyleObj = await buildEnhancedDarkStyle();
        } else {
          initialStyleObj = await buildDefaultLightStyle();
        }
      } catch (e) {
        console.warn("Could not build pre-cached style object, using default URL:", e);
      }

      if (isDisposed || !containerRef.current || mapRef.current) return;

      const map = new maplibregl.Map({
        container: containerRef.current,
        style: initialStyleObj,
        center: INITIAL_MAP_VIEW.center,
        zoom: INITIAL_MAP_VIEW.zoom,
        minZoom: INITIAL_MAP_VIEW.minZoom,
        maxZoom: INITIAL_MAP_VIEW.maxZoom,
        attributionControl: false,
      });

      mapRef.current = map;
      currentAppliedStyleRef.current = mapStyle;

      map.on("error", (e) => {
        console.error("[map error]", e.error);
      });

      map.on("load", () => {
        syncOverlayLayers(map, layers, gridPoints);
        if (onMapLoadedRef.current) {
          onMapLoadedRef.current(map);
        }
      });

      map.on("style.load", () => {
        const styleName = map.getStyle()?.name || "Unknown Style";
        console.log("[map style loaded]", styleName);
        syncOverlayLayers(map, layers, gridPoints);
      });

      // Throttled compass bearing
      let rafId: number | null = null;
      const updateBearing = () => {
        if (rafId) return;
        rafId = requestAnimationFrame(() => {
          rafId = null;
          if (mapRef.current && onBearingChangeRef.current) {
            onBearingChangeRef.current(mapRef.current.getBearing());
          }
        });
      };

      map.on("rotate", updateBearing);
      map.on("rotateend", () => {
        if (mapRef.current && onBearingChangeRef.current) {
          onBearingChangeRef.current(mapRef.current.getBearing());
        }
      });

      // Map Click
      map.on("click", (e) => {
        const lat = Number(e.lngLat.lat.toFixed(4));
        const lon = Number(e.lngLat.lng.toFixed(4));

        if (isWithinCoverageArea(lat, lon)) {
          if (onMapClickRef.current) {
            onMapClickRef.current({ lat, lon });
          }
        } else {
          if (onOutsideClickRef.current) {
            onOutsideClickRef.current();
          }
        }
      });
    };

    initializeMap();

    return () => {
      isDisposed = true;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2. Style Switching on existing map instance with { diff: false }
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (currentAppliedStyleRef.current === mapStyle) return;

    currentAppliedStyleRef.current = mapStyle;

    const switchStyle = async () => {
      try {
        if (mapStyle === "satellite") {
          const hybridStyle = await buildSatelliteHybridStyle();
          if (mapRef.current) mapRef.current.setStyle(hybridStyle, { diff: false });
        } else if (mapStyle === "dark") {
          const darkStyle = await buildEnhancedDarkStyle();
          if (mapRef.current) mapRef.current.setStyle(darkStyle, { diff: false });
        } else {
          const lightStyle = await buildDefaultLightStyle();
          if (mapRef.current) mapRef.current.setStyle(lightStyle, { diff: false });
        }
      } catch (err) {
        console.error("Failed to switch map style:", err);
      }
    };

    switchStyle();
  }, [mapStyle]);

  // 3. Sync Overlays on layers or grid points change
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    syncOverlayLayers(map, layers, gridPoints);
  }, [layers, gridPoints, syncOverlayLayers]);

  // 4. Synchronize Historical Replay Local Risk Field & Contours
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;

    const emptyFC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

    if (!activeReplay || !activeReplayHour?.local_field) {
      (map.getSource("replay-contours-source") as maplibregl.GeoJSONSource | undefined)?.setData(emptyFC);
      (map.getSource("replay-impact-zone-source") as maplibregl.GeoJSONSource | undefined)?.setData(emptyFC);
      (map.getSource("replay-rain-source") as maplibregl.GeoJSONSource | undefined)?.setData(emptyFC);
      (map.getSource("replay-storm-track-source") as maplibregl.GeoJSONSource | undefined)?.setData(emptyFC);
      return;
    }

    const { riskContours, impactZoneOutline, rainCells, stormTrack } = generateLocalFieldGeoJson(
      activeReplayHour.local_field
    );

    (map.getSource("replay-contours-source") as maplibregl.GeoJSONSource | undefined)?.setData(riskContours);
    (map.getSource("replay-impact-zone-source") as maplibregl.GeoJSONSource | undefined)?.setData(impactZoneOutline);
    (map.getSource("replay-rain-source") as maplibregl.GeoJSONSource | undefined)?.setData(rainCells);
    (map.getSource("replay-storm-track-source") as maplibregl.GeoJSONSource | undefined)?.setData(stormTrack);
  }, [activeReplay, activeReplayHour]);

  // 5. Update HTML City Markers with Alert Rings
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    cityMarkersRef.current.forEach((marker) => marker.remove());
    cityMarkersRef.current.clear();

    if (!layers.showCityPins) return;

    const citiesPredictionMap = new globalThis.Map<string, { prob: number; severity: SeverityLevel }>();
    if (citiesData?.cities) {
      Object.entries(citiesData.cities).forEach(([name, preds]) => {
        const p = preds.find((item) => item.lead_time_hours === selectedLead) || preds[0];
        if (p) {
          citiesPredictionMap.set(name.toLowerCase(), {
            prob: p.thunderstorm_probability,
            severity: (p.severity || "none") as SeverityLevel,
          });
        }
      });
    }

    const alertMap = new globalThis.Map<string, AlertResponse>();
    if (activeAlerts && activeAlerts.length > 0) {
      activeAlerts.forEach((alert) => {
        if (alert.is_active) {
          alertMap.set(alert.city.toLowerCase(), alert);
        }
      });
    }

    INDIAN_CITIES.forEach((city) => {
      const pred = citiesPredictionMap.get(city.name.toLowerCase());
      const prob = pred ? pred.prob : null;
      const severity = pred ? pred.severity : "none";
      const sevColor = SEVERITY_CONFIG[severity]?.color || "#64748b";
      const probFormatted = formatProbability(prob);

      const matchedAlert = alertMap.get(city.name.toLowerCase());
      const hasActiveAlert = layers.showAlertPins && (matchedAlert !== undefined || (prob !== null && prob >= 0.30));
      const tier = matchedAlert?.tier || (prob !== null && prob >= 0.60 ? "warning" : prob !== null && prob >= 0.40 ? "advisory" : prob !== null && prob >= 0.30 ? "watch" : null);
      const isTest = matchedAlert?.is_test || false;

      const el = document.createElement("div");
      el.className = "vajra-city-pin group flex flex-col items-center cursor-pointer select-none";
      el.style.width = "48px";
      el.style.height = "56px";

      let ringHtml = "";
      if (hasActiveAlert && tier) {
        if (tier === "warning") {
          ringHtml = `
            <div class="absolute -inset-3.5 rounded-full ${isTest ? 'bg-test-striped-subtle border-2 border-dashed border-amber-400' : 'bg-rose-500/25 border border-rose-500/80'} animate-convective-ring"></div>
            <div class="absolute -inset-2 flex items-center justify-around overflow-hidden rounded-full opacity-70 pointer-events-none">
              <span class="rain-streak-1 w-0.5 h-2.5 bg-rose-400 rounded-full"></span>
              <span class="rain-streak-2 w-0.5 h-3 bg-amber-300 rounded-full"></span>
              <span class="rain-streak-3 w-0.5 h-2.5 bg-rose-400 rounded-full"></span>
            </div>
          `;
        } else if (tier === "advisory") {
          ringHtml = `
            <div class="absolute -inset-3 rounded-full ${isTest ? 'bg-test-striped-subtle border border-dashed border-amber-400' : 'bg-orange-500/20 border border-orange-500/60'} animate-convective-ring"></div>
            <div class="absolute -inset-1.5 flex items-center justify-around overflow-hidden rounded-full opacity-60 pointer-events-none">
              <span class="rain-streak-1 w-0.5 h-2 bg-orange-400 rounded-full"></span>
              <span class="rain-streak-2 w-0.5 h-2.5 bg-amber-300 rounded-full"></span>
              <span class="rain-streak-3 w-0.5 h-2 bg-orange-400 rounded-full"></span>
            </div>
          `;
        } else if (tier === "watch") {
          ringHtml = `
            <div class="absolute -inset-2.5 rounded-full ${isTest ? 'border border-dashed border-amber-400' : 'bg-yellow-500/15 border border-yellow-500/40'} animate-pulse"></div>
          `;
        }
      }

      el.innerHTML = `
        <div class="relative flex flex-col items-center">
          ${ringHtml}
          <div class="relative flex h-8 w-8 items-center justify-center rounded-full border-2 ${isTest ? 'border-amber-400' : 'border-white'} shadow-md shadow-black/30 transition-transform duration-150 group-hover:scale-110" style="background-color: ${sevColor}">
            ${
              tier === "warning"
                ? '<svg viewBox="0 0 24 24" fill="currentColor" class="h-4 w-4 text-white drop-shadow-sm"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>'
                : '<svg viewBox="0 0 24 24" fill="white" class="h-4 w-4 drop-shadow-sm"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>'
            }
          </div>
          <div class="mt-1 flex flex-col items-center rounded-md bg-slate-950/85 px-1.5 py-0.5 text-white backdrop-blur-sm shadow-xs border ${isTest ? 'border-amber-400' : 'border-white/20'}">
            <span class="text-[10px] font-bold leading-none flex items-center gap-0.5">
              ${city.name}
            </span>
            <span class="text-[9px] font-semibold tabular-nums text-teal-300 leading-tight">${probFormatted}</span>
            ${
              isTest
                ? '<span class="mt-0.5 rounded bg-test-striped px-1 text-[7px] font-black uppercase tracking-wider text-white shadow-xs">TEST</span>'
                : ""
            }
          </div>
        </div>
      `;

      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (onSelectCityRef.current) {
          onSelectCityRef.current(city.name, city.lat, city.lon);
        }
      });

      const marker = new maplibregl.Marker({
        element: el,
        anchor: "bottom",
      })
        .setLngLat([city.lon, city.lat])
        .addTo(map);

      cityMarkersRef.current.set(city.name, marker);
    });
  }, [citiesData, activeAlerts, layers.showCityPins, layers.showAlertPins, selectedLead]);

  // 6. Update Distinct Historical Replay Marker
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!activeReplay) {
      if (replayMarkerRef.current) {
        replayMarkerRef.current.remove();
        replayMarkerRef.current = null;
      }
      return;
    }

    const currentSev = activeReplayHour?.severity || activeReplay.prediction?.severity || "moderate";
    const sevColor = SEVERITY_CONFIG[currentSev as SeverityLevel]?.color || "#a855f7";
    const probFormatted = formatProbability(activeReplayHour?.probability ?? activeReplay.prediction?.thunderstorm_probability);

    if (replayMarkerRef.current) {
      replayMarkerRef.current.remove();
      replayMarkerRef.current = null;
    }

    const el = document.createElement("div");
    el.className = "vajra-replay-pin group flex flex-col items-center cursor-pointer select-none";
    el.innerHTML = `
      <div class="relative flex flex-col items-center">
        <div class="absolute -inset-2.5 rounded-full bg-violet-500/40 animate-ping"></div>
        <div class="relative flex h-10 w-10 items-center justify-center rounded-2xl border-2 border-white shadow-xl shadow-violet-950/50 text-white font-black" style="background-color: ${sevColor}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="h-5 w-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
        </div>
        <div class="mt-1 flex flex-col items-center rounded-lg bg-violet-950/90 px-2 py-0.5 text-white backdrop-blur-md shadow-md border border-violet-400/30">
          <span class="text-[10px] font-bold leading-none tracking-wide text-violet-200">${activeReplay.city} [REPLAY]</span>
          <span class="text-[9px] font-extrabold tabular-nums text-amber-300 leading-tight">${probFormatted}</span>
        </div>
      </div>
    `;

    replayMarkerRef.current = new maplibregl.Marker({
      element: el,
      anchor: "bottom",
    })
      .setLngLat([activeReplay.longitude, activeReplay.latitude])
      .addTo(map);
  }, [activeReplay, activeReplayHour]);

  // 7. Update Selected Location Marker
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!selectedLocation) {
      if (selectedMarkerRef.current) {
        selectedMarkerRef.current.remove();
        selectedMarkerRef.current = null;
      }
      return;
    }

    if (!selectedMarkerRef.current) {
      const el = document.createElement("div");
      el.className = "vajra-selected-pin flex flex-col items-center cursor-pointer";
      el.innerHTML = `
        <div class="relative flex items-center justify-center">
          <div class="absolute -inset-2 rounded-full bg-teal-500/30 animate-ping"></div>
          <div class="h-8 w-8 rounded-2xl bg-gradient-to-tr from-teal-600 to-cyan-400 p-1.5 text-white shadow-lg shadow-teal-900/40 flex items-center justify-center border-2 border-white">
            <svg viewBox="0 0 24 24" fill="currentColor" class="w-full h-full">
              <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/>
            </svg>
          </div>
        </div>
      `;

      selectedMarkerRef.current = new maplibregl.Marker({
        element: el,
        anchor: "bottom",
      })
        .setLngLat([selectedLocation.lon, selectedLocation.lat])
        .addTo(map);
    } else {
      selectedMarkerRef.current.setLngLat([selectedLocation.lon, selectedLocation.lat]);
    }
  }, [selectedLocation]);

  // 8. Update GPS User Location Marker
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!userLocation) {
      if (userMarkerRef.current) {
        userMarkerRef.current.remove();
        userMarkerRef.current = null;
      }
      return;
    }

    if (!userMarkerRef.current) {
      const el = document.createElement("div");
      el.className = "user-location-marker relative flex items-center justify-center";
      el.innerHTML = `
        <div class="absolute h-8 w-8 rounded-full bg-sky-500/30 animate-ping"></div>
        <div class="relative h-4 w-4 rounded-full bg-sky-500 border-2 border-white shadow-md shadow-sky-900/40"></div>
      `;

      userMarkerRef.current = new maplibregl.Marker({
        element: el,
        anchor: "center",
      })
        .setLngLat([userLocation.lon, userLocation.lat])
        .addTo(map);
    } else {
      userMarkerRef.current.setLngLat([userLocation.lon, userLocation.lat]);
    }
  }, [userLocation]);

  // 9. Handle flyTo target
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !flyToTarget) return;

    map.flyTo({
      center: [flyToTarget.lon, flyToTarget.lat],
      zoom: flyToTarget.zoom ?? Math.max(map.getZoom(), 8.5),
      essential: true,
      duration: 1000,
    });
  }, [flyToTarget]);

  return (
    <div className="relative h-full w-full">
      <div
        ref={containerRef}
        id="map-root"
        className={`h-full w-full outline-none select-none ${className}`}
        style={{ minHeight: "100vh" }}
      />

      {/* Replay Mode Honest Map Caption */}
      {activeReplay && (
        <div className="pointer-events-none absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 rounded-full glass-panel-elevated px-3.5 py-1.5 text-xs font-semibold text-slate-800 dark:text-slate-100 shadow-glass border border-violet-500/30 animate-in fade-in-50">
          <span className="flex h-2 w-2 rounded-full bg-amber-400 animate-ping" />
          <span>Model risk field + archive rainfall. Not radar.</span>
        </div>
      )}
    </div>
  );
};

export const MapLibreMap = memo(MapLibreMapComponent);
