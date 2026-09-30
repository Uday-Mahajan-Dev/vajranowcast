"use client";

import React, { useMemo } from "react";
import { Building2, ChevronRight, AlertCircle, RefreshCw, Clock } from "lucide-react";
import { CitiesNowcastResponse, SeverityLevel } from "@/lib/types";
import { INDIAN_CITIES, getSeverityFromProbability, DEFAULT_DISCLAIMER } from "@/lib/constants";
import { formatISTTime, formatProbability } from "@/lib/utils";
import { SearchBar, PlaceSelection } from "../navigation/SearchBar";
import { LeadTimeOption } from "../map/LeadTimeSlider";

interface CitiesTabProps {
  data: CitiesNowcastResponse | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
  selectedLead?: LeadTimeOption;
  onSelectCity: (cityName: string, lat: number, lon: number) => void;
}

export const CitiesTab: React.FC<CitiesTabProps> = ({
  data,
  isLoading,
  error,
  onRetry,
  selectedLead = 0,
  onSelectCity,
}) => {
  const cityItems = useMemo(() => {
    if (!data?.cities) return [];

    const items = Object.entries(data.cities).map(([name, preds]) => {
      const p = preds.find((item) => item.lead_time_hours === selectedLead) || preds[0] || {};
      const prob = p.thunderstorm_probability ?? 0;
      const severity = (p.severity || "none") as SeverityLevel;
      const staticCity = INDIAN_CITIES.find((c) => c.name.toLowerCase() === name.toLowerCase());
      const state = staticCity?.state || "India";
      const lat = p.latitude || staticCity?.lat || 0;
      const lon = p.longitude || staticCity?.lon || 0;
      const temp = p.input_conditions?.temperature_2m;
      const timeIst = p.input_time_ist || p.timestamp;

      return {
        name,
        state,
        lat,
        lon,
        prob,
        severity,
        temp,
        timeIst,
      };
    });

    // Sort by thunderstorm probability descending
    return items.sort((a, b) => b.prob - a.prob);
  }, [data, selectedLead]);

  const handleSearchSelect = (place: PlaceSelection) => {
    onSelectCity(place.name, place.lat, place.lon);
  };

  return (
    <div className="space-y-4">
      {/* Search Component with Instant GeoNames + Geocoding Dropdown */}
      <div>
        <SearchBar
          variant="citiesTab"
          placeholder="Search any place, town, or district in India…"
          onSelectPlace={handleSearchSelect}
        />
      </div>

      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200/60 pb-3 dark:border-slate-800/60 pt-1">
        <div>
          <h2 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Building2 className="h-4 w-4 text-teal-600 dark:text-teal-400" />
            Top 10 Monitored Metro Hubs
          </h2>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Updated {data ? formatISTTime(data.timestamp, "timeOnly") : "Loading..."}
          </p>
        </div>
      </div>

      {/* Error State with Retry */}
      {error && !isLoading && (
        <div className="rounded-2xl border border-rose-500/20 bg-rose-500/10 p-4 text-center">
          <AlertCircle className="mx-auto h-6 w-6 text-rose-500 mb-2" />
          <p className="text-xs font-semibold text-rose-700 dark:text-rose-300">{error}</p>
          <button
            onClick={onRetry}
            className="mt-3 inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-rose-500"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}

      {/* Loading Skeletons */}
      {isLoading && (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((n) => (
            <div
              key={n}
              className="h-16 w-full animate-pulse rounded-2xl border border-slate-200/50 bg-slate-100/60 p-3 dark:border-slate-800/50 dark:bg-slate-900/40"
            />
          ))}
        </div>
      )}

      {/* 10 Major Cities List */}
      {!isLoading && !error && cityItems.length > 0 && (
        <div className="space-y-2">
          {cityItems.map((city, idx) => {
            const sevMeta = getSeverityFromProbability(city.prob);
            return (
              <button
                key={city.name}
                onClick={() => onSelectCity(city.name, city.lat, city.lon)}
                className="group flex w-full items-center justify-between rounded-2xl border border-slate-200/70 bg-white/70 p-3 text-left transition-all hover:border-teal-500/40 hover:bg-teal-50/40 dark:border-slate-800/80 dark:bg-slate-900/60 dark:hover:bg-slate-800/60 shadow-xs"
              >
                <div className="flex items-center gap-3">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-xs font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                    {idx + 1}
                  </div>
                  <div>
                    <div className="font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                      {city.name}
                      {city.temp !== undefined && (
                        <span className="text-xs font-normal text-slate-400">
                          {city.temp.toFixed(1)}°C
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-400">{city.state}</div>
                  </div>
                </div>

                <div className="flex items-center gap-2.5">
                  <div className="text-right">
                    <div className="text-sm font-bold tabular-nums text-slate-900 dark:text-white">
                      {formatProbability(city.prob)}
                    </div>
                    <span
                      className={`inline-block rounded px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider ${sevMeta.chipClass}`}
                    >
                      {sevMeta.shortLabel}
                    </span>
                  </div>
                  <ChevronRight className="h-4 w-4 text-slate-300 transition-transform group-hover:translate-x-0.5 dark:text-slate-600" />
                </div>
              </button>
            );
          })}
        </div>
      )}

      <div className="rounded-xl bg-slate-100/70 p-2 text-[10px] text-slate-500 dark:bg-slate-900/50 dark:text-slate-400">
        {DEFAULT_DISCLAIMER}
      </div>
    </div>
  );
};
