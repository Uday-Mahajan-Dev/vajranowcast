"use client";

import React from "react";
import {
  TrendingUp,
  ShieldAlert,
  Clock,
  Sparkles,
  MapPin,
  ChevronRight,
  ArrowLeft,
  Loader2,
  Building2,
  Bell,
  History,
  Info,
} from "lucide-react";
import {
  CitiesNowcastResponse,
  NowcastResponse,
  SeverityLevel,
  AlertResponse,
  HistoricalReplayEvent,
  ReplayTimelineHour,
  ModelInfo,
  DataSourceStatus,
} from "@/lib/types";
import {
  DEFAULT_DISCLAIMER,
  getSeverityFromProbability,
  INDIAN_CITIES,
} from "@/lib/constants";
import { formatISTTime, formatProbability, formatValidityWindow } from "@/lib/utils";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { CitiesTab } from "../tabs/CitiesTab";
import { AlertsTab } from "../tabs/AlertsTab";
import { ReplaysTab } from "../tabs/ReplaysTab";
import { AboutTab } from "../tabs/AboutTab";
import { ActiveTab } from "../navigation/TabBar";
import { PlaceCard } from "./PlaceCard";
import { ReplayCard } from "./ReplayCard";
import { LeadTimeOption } from "../map/LeadTimeSlider";

import { CustomBottomSheet, SnapLevel } from "./CustomBottomSheet";

interface ResponsiveSheetProps {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  activeSnapPoint?: number | string | null;
  onSnapPointChange?: (snap: number | string | null) => void;
  selectedPlaceName?: string | null;
  selectedCoordinates?: { lat: number; lon: number } | null;
  selectedNowcast?: NowcastResponse | null;
  isLoadingNowcast?: boolean;
  nowcastError?: string | null;
  selectedLead: LeadTimeOption;
  onSelectLead: (lead: LeadTimeOption) => void;
  activeReplay?: HistoricalReplayEvent | null;
  onExitReplay: () => void;
  onReplayHourSelect?: (hour: ReplayTimelineHour) => void;
  citiesData?: CitiesNowcastResponse | null;
  isLoadingCities?: boolean;
  citiesError?: string | null;
  activeAlerts?: AlertResponse[];
  isLoadingAlerts?: boolean;
  alertsError?: string | null;
  lastCheckedAlertsTime?: Date;
  replaysData?: HistoricalReplayEvent[];
  isLoadingReplays?: boolean;
  replaysError?: string | null;
  modelInfo?: ModelInfo | null;
  sourcesStatus?: DataSourceStatus[];
  isLoadingAbout?: boolean;
  onRetryCities: () => void;
  onRetryAlerts: () => void;
  onRetryReplays: () => void;
  onRetryNowcast: () => void;
  onSelectCity: (cityName: string, lat?: number, lon?: number) => void;
  onSelectReplay: (event: HistoricalReplayEvent) => void;
  onClearSelectedPlace: () => void;
}

export const ResponsiveSheet: React.FC<ResponsiveSheetProps> = ({
  isOpen,
  onOpenChange,
  activeTab,
  onTabChange,
  activeSnapPoint = 0.55,
  onSnapPointChange,
  selectedPlaceName = null,
  selectedCoordinates = null,
  selectedNowcast = null,
  isLoadingNowcast = false,
  nowcastError = null,
  selectedLead = 0,
  onSelectLead,
  activeReplay = null,
  onExitReplay,
  onReplayHourSelect,
  citiesData = null,
  isLoadingCities = false,
  citiesError = null,
  activeAlerts = [],
  isLoadingAlerts = false,
  alertsError = null,
  lastCheckedAlertsTime,
  replaysData = [],
  isLoadingReplays = false,
  replaysError = null,
  modelInfo = null,
  sourcesStatus = [],
  isLoadingAbout = false,
  onRetryCities,
  onRetryAlerts,
  onRetryReplays,
  onRetryNowcast,
  onSelectCity,
  onSelectReplay,
  onClearSelectedPlace,
}) => {
  const isDesktop = useMediaQuery("(min-width: 1024px)");

  // Convert snap point to SnapLevel
  const currentSnap: SnapLevel =
    activeSnapPoint === 0.18 || activeSnapPoint === "peek"
      ? "peek"
      : activeSnapPoint === 0.92 || activeSnapPoint === "full"
      ? "full"
      : "half";

  const handleSnapChange = (snap: SnapLevel) => {
    if (onSnapPointChange) {
      if (snap === "peek") onSnapPointChange(0.18);
      else if (snap === "full") onSnapPointChange(0.92);
      else onSnapPointChange(0.55);
    }
  };

  // Top 5 high-risk cities for Map Overview
  const topCities = React.useMemo(() => {
    if (!citiesData?.cities) return [];

    const list = Object.entries(citiesData.cities).map(([name, preds]) => {
      const p = preds.find((item) => item.lead_time_hours === selectedLead) || preds[0] || {};
      const prob = p.thunderstorm_probability ?? 0;
      const severity = (p.severity || "none") as SeverityLevel;
      const staticCity = INDIAN_CITIES.find((c) => c.name.toLowerCase() === name.toLowerCase());
      const state = staticCity?.state || "India";
      const lat = p.latitude || staticCity?.lat || 0;
      const lon = p.longitude || staticCity?.lon || 0;
      const temp = p.input_conditions?.temperature_2m;
      return { name, state, lat, lon, prob, severity, temp };
    });

    return list.sort((a, b) => b.prob - a.prob).slice(0, 5);
  }, [citiesData, selectedLead]);

  // Map Overview Content (Default when no place or replay is active)
  const mapOverviewContent = (
    <div className="space-y-4">
      {/* Title / Summary */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-900 dark:text-white">
            India Convective Radar
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {selectedLead === 0 ? "Current Nowcast (Lead 0)" : `+${selectedLead}h Forecast Window`}
          </p>
        </div>
        <div className="flex items-center gap-1 text-[11px] font-semibold text-teal-600 dark:text-teal-400">
          <Clock className="h-3 w-3" />
          <span>{formatISTTime(new Date(), "short")}</span>
        </div>
      </div>

      {/* Active Alerts Banner if any */}
      {activeAlerts.length > 0 && (() => {
        const hasTest = activeAlerts.some((a) => a.is_test);
        const hasWarning = activeAlerts.some((a) => a.tier === "warning" || (!a.tier && a.thunderstorm_probability >= 0.60));

        return (
          <div
            onClick={() => onTabChange("alerts")}
            className={`flex cursor-pointer items-center justify-between rounded-2xl border p-3 transition-all ${
              hasTest
                ? "border-amber-500/40 bg-amber-500/10 text-amber-950 dark:text-amber-200 hover:bg-amber-500/15"
                : hasWarning
                ? "border-red-500/40 bg-red-500/10 text-red-950 dark:text-red-200 hover:bg-red-500/15"
                : "border-orange-500/40 bg-orange-500/10 text-orange-950 dark:text-orange-200 hover:bg-orange-500/15"
            }`}
          >
            <div className="flex items-center gap-2">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-xl text-white shadow-sm ${
                  hasTest ? "bg-amber-500" : hasWarning ? "bg-red-600" : "bg-orange-500"
                }`}
              >
                {hasWarning ? <ShieldAlert className="h-4 w-4" /> : <Bell className="h-4 w-4" />}
              </div>
              <div>
                <div className="text-xs font-bold flex items-center gap-1.5">
                  <span>
                    {activeAlerts.length} Active {hasWarning ? "Warning / Alert" : "Convective Alert"}
                    {activeAlerts.length !== 1 ? "s" : ""}
                  </span>
                  {hasTest && (
                    <span className="rounded bg-test-striped px-1.5 py-0.2 text-[8px] font-black uppercase text-white shadow-xs">
                      TEST DRILL
                    </span>
                  )}
                </div>
                <div className="text-[10px] opacity-80">
                  {hasTest
                    ? "Simulated drill alert active (expires in 15m) — tap to view"
                    : "Tap to view operational nowcast warnings"}
                </div>
              </div>
            </div>
            <ChevronRight className="h-4 w-4 text-slate-400" />
          </div>
        );
      })()}

      {/* Top Monitored Hubs Card */}
      <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
        <div className="flex items-center justify-between pb-2">
          <div className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
            High Convective Threat Cities ({selectedLead === 0 ? "Now" : `+${selectedLead}h`})
          </div>
          <button
            onClick={() => onTabChange("cities")}
            className="text-[11px] font-semibold text-teal-600 hover:underline dark:text-teal-400"
          >
            All 10 Cities →
          </button>
        </div>

        {isLoadingCities && (
          <div className="space-y-2 py-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-10 w-full animate-pulse rounded-xl bg-slate-200/70 dark:bg-slate-800/60" />
            ))}
          </div>
        )}

        {!isLoadingCities && topCities.length > 0 && (
          <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {topCities.map((city) => {
              const sev = getSeverityFromProbability(city.prob);
              return (
                <div
                  key={city.name}
                  onClick={() => onSelectCity(city.name, city.lat, city.lon)}
                  className="flex cursor-pointer items-center justify-between py-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40 rounded-lg px-1.5"
                >
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-500/10 text-teal-600 dark:bg-teal-500/15 dark:text-teal-400 font-bold text-xs">
                      {city.name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <div className="text-xs font-bold text-slate-900 dark:text-white">
                        {city.name}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {city.temp !== undefined ? `${city.temp.toFixed(1)}°C • ` : ""}{city.state}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-black ${sev.chipClass}`}>
                      {formatProbability(city.prob)}
                    </span>
                    <span className={`text-[10px] font-semibold hidden sm:inline ${sev.textClass}`}>
                      {sev.shortLabel}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Replays Teaser */}
      {replaysData.length > 0 && (
        <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-3.5 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-violet-600 dark:text-violet-400" />
              <span className="text-xs font-bold text-slate-900 dark:text-white">
                Historical Storm Replays
              </span>
            </div>
            <button
              onClick={() => onTabChange("replays")}
              className="text-[11px] font-semibold text-teal-600 hover:underline dark:text-teal-400"
            >
              Explore {replaysData.length} Cases →
            </button>
          </div>
        </div>
      )}

      {/* Model Disclaimer */}
      <div className="rounded-xl bg-slate-100/80 p-2.5 text-[11px] text-slate-500 dark:bg-slate-900/60 dark:text-slate-400 border border-slate-200/50 dark:border-slate-800/50">
        <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-300">
          <Sparkles className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400" />
          Model VajraNowcast v1.1.0
        </div>
        <p className="mt-0.5 leading-relaxed">{DEFAULT_DISCLAIMER}</p>
      </div>
    </div>
  );

  // Dynamic Content Router
  const renderContent = () => {
    // 1. Historical Replay Mode
    if (activeReplay) {
      return (
        <ReplayCard
          replay={activeReplay}
          onExit={onExitReplay}
          onHourSelect={onReplayHourSelect}
        />
      );
    }

    // 2. Selected Place Card
    if (selectedPlaceName) {
      return (
        <PlaceCard
          placeName={selectedPlaceName}
          coordinates={selectedCoordinates}
          nowcastData={selectedNowcast}
          isLoading={isLoadingNowcast}
          error={nowcastError}
          selectedLead={selectedLead}
          onSelectLead={onSelectLead}
          onBack={onClearSelectedPlace}
          onRetry={onRetryNowcast}
        />
      );
    }

    // 3. Tab Views
    switch (activeTab) {
      case "cities":
        return (
          <CitiesTab
            data={citiesData}
            isLoading={isLoadingCities}
            error={citiesError}
            onRetry={onRetryCities}
            selectedLead={selectedLead}
            onSelectCity={(name, lat, lon) => {
              onSelectCity(name, lat, lon);
              onTabChange("map");
            }}
          />
        );
      case "alerts":
        return (
          <AlertsTab
            alerts={activeAlerts}
            isLoading={isLoadingAlerts}
            error={alertsError}
            lastCheckedTime={lastCheckedAlertsTime}
            onRetry={onRetryAlerts}
            onSelectAlertCity={(name, lat, lon) => {
              onSelectCity(name, lat, lon);
              onTabChange("map");
            }}
          />
        );
      case "replays":
        return (
          <ReplaysTab
            replays={replaysData}
            isLoading={isLoadingReplays}
            error={replaysError}
            onRetry={onRetryReplays}
            onSelectReplay={(event) => {
              onSelectReplay(event);
            }}
          />
        );
      case "about":
        return (
          <AboutTab
            modelInfo={modelInfo}
            sourcesStatus={sourcesStatus}
            isLoading={isLoadingAbout}
          />
        );
      case "map":
      default:
        return mapOverviewContent;
    }
  };

  return (
    <>
      {/* 1. Desktop: ONLY Left Side Panel (≥ 1024px) */}
      {isDesktop && (
        <aside
          id="desktop-side-panel"
          aria-label="Nowcast Information Panel"
          className="fixed bottom-4 left-24 top-20 z-30 flex w-[400px] flex-col overflow-hidden rounded-3xl glass-panel-elevated shadow-glass-elevated animate-in fade-in-50 slide-in-from-left-4"
        >
          <div className="flex-1 overflow-y-auto p-5 scrollbar-thin">
            {renderContent()}
          </div>
        </aside>
      )}

      {/* 2. Mobile: Custom Non-Modal Bottom Sheet (< 1024px) */}
      {!isDesktop && (
        <CustomBottomSheet
          snapLevel={currentSnap}
          onSnapChange={handleSnapChange}
        >
          {renderContent()}
        </CustomBottomSheet>
      )}
    </>
  );
};
