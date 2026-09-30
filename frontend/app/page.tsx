"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import dynamic from "next/dynamic";
import { useSearchParams, useRouter } from "next/navigation";
import { SearchBar, PlaceSelection } from "@/components/navigation/SearchBar";
import { ControlStack } from "@/components/navigation/ControlStack";
import { TabBar, ActiveTab } from "@/components/navigation/TabBar";
import { NavigationRail } from "@/components/navigation/NavigationRail";
import { MapTypeModal, MapLayerSettings } from "@/components/map/MapTypeModal";
import { ResponsiveSheet } from "@/components/sheet/ResponsiveSheet";
import { AttributionButton } from "@/components/common/AttributionButton";
import { MapLegend } from "@/components/map/MapLegend";
import { LeadTimeSlider, LeadTimeOption } from "@/components/map/LeadTimeSlider";
import { MapStyleId, INDIAN_CITIES, OUTSIDE_COVERAGE_MESSAGE } from "@/lib/constants";
import {
  fetchCitiesNowcast,
  fetchActiveAlerts,
  fetchNowcast,
  fetchNowcastWithClientFallback,
  fetchGrid,
  fetchHistoricalReplays,
  fetchModelInfo,
  fetchSourcesStatus,
} from "@/lib/api";
import {
  CitiesNowcastResponse,
  ActiveAlertsResponse,
  NowcastResponse,
  GridPointPrediction,
  HistoricalReplayEvent,
  ReplayTimelineHour,
  ModelInfo,
  DataSourceStatus,
} from "@/lib/types";
import { lookupPlaceName } from "@/lib/reverse_lookup";
import { getCachedNowcast, setCachedNowcast } from "@/lib/cache";
import { AlertCircle, CloudLightning } from "lucide-react";
import type { Map as MapInstance } from "maplibre-gl";

// 1. Dynamic import of MapLibreMap at MODULE TOP LEVEL (ssr: false)
const MapLibreMap = dynamic(
  () => import("@/components/map/MapLibreMap").then((mod) => mod.MapLibreMap),
  {
    ssr: false,
    loading: () => (
      <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-950 text-white">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-500/15 text-teal-400 border border-teal-500/20 mb-3 animate-pulse">
          <CloudLightning className="h-6 w-6" />
        </div>
        <p className="text-xs font-semibold text-slate-400">Loading VajraNowcast Map Engine…</p>
      </div>
    ),
  }
);

function HomePageContent() {
  // Router & Tab state
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab") as ActiveTab | null;

  const [activeTab, setActiveTab] = useState<ActiveTab>(
    tabParam && ["map", "cities", "alerts", "replays", "about", "staff"].includes(tabParam)
      ? tabParam
      : "map"
  );

  // Drawer Snap State (Mobile): 0.18 (peek), 0.55 (half), 0.92 (full)
  const [activeSnapPoint, setActiveSnapPoint] = useState<number | string | null>(0.55);
  const [isBottomSheetOpen, setIsBottomSheetOpen] = useState(true);

  // Sync tab with URL query parameter & handle mobile snap behavior
  const handleTabChange = useCallback(
    (tab: ActiveTab) => {
      if (tab === activeTab) {
        // Tapping active tab toggles between peek and half
        setActiveSnapPoint((prev) => (prev === 0.18 ? 0.55 : 0.18));
      } else {
        setActiveTab(tab);
        setActiveSnapPoint(0.55);
        setIsBottomSheetOpen(true);
        const url = tab === "map" ? "/" : `/?tab=${tab}`;
        window.history.replaceState(null, "", url);
      }
    },
    [activeTab]
  );

  // UI Theme & Map Style
  const [themePreference, setThemePreference] = useState<"light" | "dark" | "system">("dark");
  const [mapStyle, setMapStyle] = useState<MapStyleId>("default");
  const [isLayersModalOpen, setIsLayersModalOpen] = useState(false);
  const [isLocating, setIsLocating] = useState(false);
  const [outsideCoverageToast, setOutsideCoverageToast] = useState(false);
  const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Map & Camera Controls
  const mapInstanceRef = useRef<MapInstance | null>(null);
  const [compassBearing, setCompassBearing] = useState(0);
  const [flyToTarget, setFlyToTarget] = useState<{ lat: number; lon: number; zoom?: number } | null>(null);

  // Overlays & Lead Time (BUG 1: Default to 0 "Now")
  const [selectedLead, setSelectedLead] = useState<LeadTimeOption>(0);
  const [layers, setLayers] = useState<MapLayerSettings>({
    showHeatmap: false,
    showGridPoints: true,
    showCityPins: true,
    showAlertPins: true,
    show3DBuildings: false,
  });

  // Selected Place State
  const [selectedPlace, setSelectedPlace] = useState<{ name: string; lat: number; lon: number } | null>(null);
  const [userLocation, setUserLocation] = useState<{ lat: number; lon: number } | null>(null);
  const [nowcastData, setNowcastData] = useState<NowcastResponse | null>(null);
  const [isLoadingNowcast, setIsLoadingNowcast] = useState(false);
  const [nowcastError, setNowcastError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Replay Mode State (BUG 2)
  const [activeReplay, setActiveReplay] = useState<HistoricalReplayEvent | null>(null);
  const [activeReplayHour, setActiveReplayHour] = useState<ReplayTimelineHour | null>(null);

  // Data States
  const [gridPoints, setGridPoints] = useState<GridPointPrediction[]>([]);
  const [citiesData, setCitiesData] = useState<CitiesNowcastResponse | null>(null);
  const [isLoadingCities, setIsLoadingCities] = useState(true);
  const [citiesError, setCitiesError] = useState<string | null>(null);

  const [activeAlerts, setActiveAlerts] = useState<any[]>([]);
  const [isLoadingAlerts, setIsLoadingAlerts] = useState(true);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [lastCheckedAlertsTime, setLastCheckedAlertsTime] = useState<Date>(new Date());

  const [replaysData, setReplaysData] = useState<HistoricalReplayEvent[]>([]);
  const [isLoadingReplays, setIsLoadingReplays] = useState(false);
  const [replaysError, setReplaysError] = useState<string | null>(null);

  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [sourcesStatus, setSourcesStatus] = useState<DataSourceStatus[]>([]);
  const [isLoadingAbout, setIsLoadingAbout] = useState(false);

  // Load saved theme and style from localStorage
  useEffect(() => {
    try {
      const savedTheme = localStorage.getItem("vajra_theme_mode") as "light" | "dark" | "system" | null;
      if (savedTheme) setThemePreference(savedTheme);

      const savedStyle = localStorage.getItem("vajra_map_style") as MapStyleId | null;
      if (savedStyle && ["default", "dark", "satellite"].includes(savedStyle)) {
        setMapStyle(savedStyle);
      }
    } catch {
      // Ignore
    }
  }, []);

  // Synchronize UI Chrome Theme
  useEffect(() => {
    const root = document.documentElement;
    let isDark = false;

    if (themePreference === "dark") {
      isDark = true;
    } else if (themePreference === "light") {
      isDark = false;
    } else if (themePreference === "system") {
      if (mapStyle === "dark") {
        isDark = true;
      } else {
        isDark =
          typeof window !== "undefined" &&
          window.matchMedia("(prefers-color-scheme: dark)").matches;
      }
    }

    if (isDark) {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }

    try {
      localStorage.setItem("vajra_theme_mode", themePreference);
    } catch {
      // Ignore
    }
  }, [themePreference, mapStyle]);

  const handleSelectStyle = useCallback((styleId: MapStyleId) => {
    setMapStyle(styleId);
    try {
      localStorage.setItem("vajra_map_style", styleId);
    } catch {
      // Ignore
    }
  }, []);

  const handleToggleLayer = useCallback((layerKey: keyof MapLayerSettings) => {
    setLayers((prev) => ({
      ...prev,
      [layerKey]: !prev[layerKey],
    }));
  }, []);

  // Fetch Cities Nowcast Data
  const loadCitiesData = useCallback(async () => {
    setIsLoadingCities(true);
    setCitiesError(null);
    try {
      const res = await fetchCitiesNowcast();
      setCitiesData(res);
    } catch (err: any) {
      console.warn("Cities data fetch failed:", err);
      setCitiesError(err.message || "Failed to load cities nowcasts");
    } finally {
      setIsLoadingCities(false);
    }
  }, []);

  // Fetch Active Alerts Data (Refetched every 5 min)
  const loadAlertsData = useCallback(async () => {
    setIsLoadingAlerts(true);
    setAlertsError(null);
    try {
      const res = await fetchActiveAlerts();
      setActiveAlerts(res.alerts || []);
      setLastCheckedAlertsTime(new Date());
    } catch (err: any) {
      if (err?.name === "AbortError" || err?.message?.toLowerCase().includes("abort")) {
        return;
      }
      console.warn("Alerts data fetch failed:", err);
      setAlertsError(err.message || "Failed to load active alerts");
    } finally {
      setIsLoadingAlerts(false);
    }
  }, []);

  // Fetch Precomputed Regional Grid Points
  const loadGridData = useCallback(async () => {
    try {
      const res = await fetchGrid();
      if (res?.points) {
        setGridPoints(res.points);
      }
    } catch (err: any) {
      if (err?.name === "AbortError" || err?.message?.toLowerCase().includes("abort")) return;
      console.warn("Grid data fetch failed:", err);
    }
  }, []);

  // Fetch Replays Data on demand
  const loadReplaysData = useCallback(async () => {
    if (replaysData.length > 0) return;
    setIsLoadingReplays(true);
    setReplaysError(null);
    try {
      const res = await fetchHistoricalReplays();
      setReplaysData(res);
    } catch (err: any) {
      if (err?.name === "AbortError" || err?.message?.toLowerCase().includes("abort")) return;
      console.warn("Replays data fetch failed:", err);
      setReplaysError(err.message || "Failed to load historical replays");
    } finally {
      setIsLoadingReplays(false);
    }
  }, [replaysData.length]);

  // Fetch Model Info & Sources Status
  const loadAboutData = useCallback(async () => {
    setIsLoadingAbout(true);
    try {
      const [mInfo, sStatus] = await Promise.allSettled([
        fetchModelInfo(),
        fetchSourcesStatus(),
      ]);
      if (mInfo.status === "fulfilled") setModelInfo(mInfo.value);
      if (sStatus.status === "fulfilled") setSourcesStatus(sStatus.value);
    } catch (err: any) {
      if (err?.name === "AbortError" || err?.message?.toLowerCase().includes("abort")) return;
      console.warn("Model info fetch failed:", err);
    } finally {
      setIsLoadingAbout(false);
    }
  }, []);

  // Initial Fetch & 5-minute Alerts Interval
  useEffect(() => {
    loadCitiesData();
    loadAlertsData();
    loadGridData();
    loadAboutData(); // Fetch model metadata and thresholds as single source of truth

    const alertsInterval = setInterval(loadAlertsData, 5 * 60 * 1000);
    return () => clearInterval(alertsInterval);
  }, [loadCitiesData, loadAlertsData, loadGridData, loadAboutData]);

  // Load Tab Data when active tab changes
  useEffect(() => {
    if (activeTab === "replays") {
      loadReplaysData();
    } else if (activeTab === "about") {
      loadAboutData();
    }
  }, [activeTab, loadReplaysData, loadAboutData]);

  // Selection & Nowcast Trigger with 0.25° Cache + AbortController
  const handleSelectPlace = useCallback(
    async (place: { name?: string; lat: number; lon: number }) => {
      // Exit replay mode if active
      setActiveReplay(null);
      setActiveReplayHour(null);

      // Abort previous in-flight request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      const placeName = place.name || (await lookupPlaceName(place.lat, place.lon));
      setSelectedPlace({ name: placeName, lat: place.lat, lon: place.lon });
      setFlyToTarget({ lat: place.lat, lon: place.lon, zoom: 8.5 });
      setIsBottomSheetOpen(true);
      setActiveSnapPoint(0.55);
      setNowcastError(null);

      // Check Spatial Cache
      const cached = getCachedNowcast(place.lat, place.lon);
      if (cached) {
        setNowcastData(cached);
        setIsLoadingNowcast(false);
        return;
      }

      setIsLoadingNowcast(true);
      try {
        const pred = await fetchNowcastWithClientFallback(
          place.lat,
          place.lon,
          [0, 1, 2, 3, 6],
          abortControllerRef.current?.signal
        );
        setNowcastData(pred);
        setCachedNowcast(place.lat, place.lon, pred);
      } catch (err: any) {
        if (err.name !== "AbortError") {
          console.warn("Failed to fetch point nowcast:", err);
          setNowcastError(err.message || "Failed to load nowcast for this location.");
        }
      } finally {
        setIsLoadingNowcast(false);
      }
    },
    []
  );

  const handleSelectCity = useCallback(
    (cityName: string, lat?: number, lon?: number) => {
      if (lat !== undefined && lon !== undefined) {
        handleSelectPlace({ name: cityName, lat, lon });
      } else {
        const city = INDIAN_CITIES.find((c) => c.name.toLowerCase() === cityName.toLowerCase());
        if (city) {
          handleSelectPlace({ name: city.name, lat: city.lat, lon: city.lon });
        }
      }
    },
    [handleSelectPlace]
  );

  // BUG 2: Handle Historical Replay Selection (Enter Replay Mode - NO /nowcast call)
  const handleSelectReplay = useCallback(
    (event: HistoricalReplayEvent) => {
      setSelectedPlace(null);
      setNowcastData(null);
      setActiveReplay(event);
      const repHour = event.timeline?.find((t) => t.is_replay_hour) || event.timeline?.[0] || null;
      setActiveReplayHour(repHour);

      setFlyToTarget({ lat: event.latitude, lon: event.longitude, zoom: 8.5 });
      setActiveTab("map");
      setIsBottomSheetOpen(true);
      setActiveSnapPoint(0.55);
      window.history.replaceState(null, "", "/?tab=map");
    },
    []
  );

  const handleExitReplay = useCallback(() => {
    setActiveReplay(null);
    setActiveReplayHour(null);
  }, []);

  // Map Click
  const handleMapClick = useCallback(
    async (loc: { lat: number; lon: number }) => {
      const friendlyName = await lookupPlaceName(loc.lat, loc.lon);
      handleSelectPlace({
        name: friendlyName,
        lat: loc.lat,
        lon: loc.lon,
      });
    },
    [handleSelectPlace]
  );

  const handleOutsideClick = useCallback(() => {
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    setOutsideCoverageToast(true);
    toastTimeoutRef.current = setTimeout(() => {
      setOutsideCoverageToast(false);
    }, 3500);
  }, []);

  const handleBearingChange = useCallback((b: number) => {
    setCompassBearing(b);
  }, []);

  const handleResetNorth = useCallback(() => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.easeTo({ bearing: 0, pitch: 0, duration: 500 });
    }
  }, []);

  const handleZoomIn = useCallback(() => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.zoomIn({ duration: 300 });
    }
  }, []);

  const handleZoomOut = useCallback(() => {
    if (mapInstanceRef.current) {
      mapInstanceRef.current.zoomOut({ duration: 300 });
    }
  }, []);

  const handleLocateMe = useCallback(() => {
    if (!navigator.geolocation) {
      alert("Geolocation is not supported by your browser.");
      return;
    }
    setIsLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setIsLocating(false);
        const { latitude, longitude } = pos.coords;
        setUserLocation({ lat: latitude, lon: longitude });
        setFlyToTarget({ lat: latitude, lon: longitude, zoom: 10 });
      },
      (err) => {
        setIsLocating(false);
        console.warn("Geolocation failed:", err);
        alert("Unable to retrieve your location. Please check browser permissions.");
      },
      { timeout: 10000, enableHighAccuracy: true }
    );
  }, []);

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-slate-950 font-sans">
      {/* 1. MapLibre Single-Instance Map Component */}
      <MapLibreMap
        mapStyle={mapStyle}
        selectedLocation={selectedPlace ? { lat: selectedPlace.lat, lon: selectedPlace.lon, name: selectedPlace.name } : null}
        userLocation={userLocation}
        flyToTarget={flyToTarget}
        layers={layers}
        gridPoints={gridPoints}
        citiesData={citiesData}
        activeAlerts={activeAlerts}
        selectedLead={selectedLead}
        activeReplay={activeReplay}
        activeReplayHour={activeReplayHour}
        onMapClick={handleMapClick}
        onSelectCity={handleSelectCity}
        onOutsideClick={handleOutsideClick}
        onBearingChange={handleBearingChange}
        onMapLoaded={(m) => {
          mapInstanceRef.current = m;
        }}
      />

      {/* 2. Top Floating Search Bar */}
      <SearchBar
        onSelectPlace={(place: PlaceSelection) => {
          handleSelectPlace({
            name: place.name,
            lat: place.lat,
            lon: place.lon,
          });
        }}
      />

      {/* 3. Lead Time Selector Bar (Top Center) */}
      <LeadTimeSlider
        currentLead={selectedLead}
        onChangeLead={setSelectedLead}
        isGridLeadFixed={true}
      />

      {/* 4. Outside Coverage Area Banner */}
      {outsideCoverageToast && (
        <div className="fixed top-28 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 rounded-2xl bg-amber-500/95 px-4 py-2.5 text-xs font-bold text-slate-950 shadow-2xl backdrop-blur-md animate-in fade-in slide-in-from-top-4">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{OUTSIDE_COVERAGE_MESSAGE}</span>
        </div>
      )}

      {/* 5. Right Edge Floating Control Stack */}
      <ControlStack
        onOpenLayers={() => setIsLayersModalOpen(true)}
        onLocateMe={handleLocateMe}
        onResetNorth={handleResetNorth}
        onZoomIn={handleZoomIn}
        onZoomOut={handleZoomOut}
        bearing={compassBearing}
        isLocating={isLocating}
      />

      {/* 6. Desktop Navigation Rail (>= 1024px) */}
      <NavigationRail
        activeTab={activeTab}
        onTabChange={handleTabChange}
        activeAlertCount={activeAlerts.length}
        theme={themePreference}
        onThemeChange={setThemePreference}
      />

      {/* 7. Mobile Bottom Tab Bar (< 1024px) */}
      <TabBar
        activeTab={activeTab}
        onTabChange={handleTabChange}
        activeAlertCount={activeAlerts.length}
      />

      {/* 8. Responsive Sheet (Exclusive Side Panel on Desktop, Vaul Bottom Sheet on Mobile) */}
      <ResponsiveSheet
        isOpen={isBottomSheetOpen}
        onOpenChange={setIsBottomSheetOpen}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        activeSnapPoint={activeSnapPoint}
        onSnapPointChange={setActiveSnapPoint}
        selectedPlaceName={selectedPlace?.name}
        selectedCoordinates={selectedPlace ? { lat: selectedPlace.lat, lon: selectedPlace.lon } : null}
        selectedNowcast={nowcastData}
        isLoadingNowcast={isLoadingNowcast}
        nowcastError={nowcastError}
        selectedLead={selectedLead}
        onSelectLead={setSelectedLead}
        activeReplay={activeReplay}
        onExitReplay={handleExitReplay}
        onReplayHourSelect={setActiveReplayHour}
        citiesData={citiesData}
        isLoadingCities={isLoadingCities}
        citiesError={citiesError}
        activeAlerts={activeAlerts}
        isLoadingAlerts={isLoadingAlerts}
        alertsError={alertsError}
        lastCheckedAlertsTime={lastCheckedAlertsTime}
        replaysData={replaysData}
        isLoadingReplays={isLoadingReplays}
        replaysError={replaysError}
        modelInfo={modelInfo}
        sourcesStatus={sourcesStatus}
        isLoadingAbout={isLoadingAbout}
        onRetryCities={loadCitiesData}
        onRetryAlerts={loadAlertsData}
        onRetryReplays={loadReplaysData}
        onRetryNowcast={() => selectedPlace && handleSelectPlace(selectedPlace)}
        onSelectCity={handleSelectCity}
        onSelectReplay={handleSelectReplay}
        onClearSelectedPlace={() => {
          setSelectedPlace(null);
          setNowcastData(null);
        }}
      />

      {/* 9. Collapsible Map Legend (Bottom Right) */}
      <MapLegend showHeatmap={layers.showHeatmap} />

      {/* 10. Collapsible Attribution & Disclaimer Button (Bottom Left) */}
      <AttributionButton currentStyle={mapStyle} />

      {/* 11. Map Type & Overlays Modal */}
      <MapTypeModal
        isOpen={isLayersModalOpen}
        onClose={() => setIsLayersModalOpen(false)}
        currentStyle={mapStyle}
        onSelectStyle={handleSelectStyle}
        layers={layers}
        onToggleLayer={handleToggleLayer}
      />
    </main>
  );
}

export default function HomePage() {
  return (
    <React.Suspense
      fallback={
        <div className="h-screen w-screen bg-slate-950 flex items-center justify-center text-white">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-500/15 text-teal-400 border border-teal-500/20 mb-3 animate-pulse">
            <CloudLightning className="h-6 w-6" />
          </div>
        </div>
      }
    >
      <HomePageContent />
    </React.Suspense>
  );
}
