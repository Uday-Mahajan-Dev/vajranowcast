"use client";

import React from "react";
import { Info, Sparkles, ShieldAlert, Database, Cpu, Layers } from "lucide-react";
import { ModelInfo, DataSourceStatus } from "@/lib/types";
import { DEFAULT_DISCLAIMER, OPTIMAL_THRESHOLD, ALERT_THRESHOLD, MAP_ATTRIBUTIONS } from "@/lib/constants";

interface AboutTabProps {
  modelInfo: ModelInfo | null;
  sourcesStatus: DataSourceStatus[];
  isLoading: boolean;
}

const DEFAULT_SOURCES: DataSourceStatus[] = [
  {
    source_name: "Open-Meteo High-Resolution NWP",
    status: "active",
    last_updated: new Date().toISOString(),
    variables: [
      "temperature_2m",
      "relative_humidity_2m",
      "surface_pressure",
      "wind_speed_10m",
      "cape",
      "convective_inhibition",
      "precipitation",
    ],
  },
  {
    source_name: "NOAA GFS 0.25° Global Forecast",
    status: "planned",
    last_updated: new Date().toISOString(),
    variables: ["HGT_clb", "CAPE_sfc", "CIN_sfc", "PWAT_ea"],
  },
  {
    source_name: "ISRO MOSDAC INSAT-3D/3DR",
    status: "planned",
    last_updated: new Date().toISOString(),
    variables: ["Cloud Top Brightness Temp", "Water Vapor", "Rainfall Rate"],
  },
  {
    source_name: "Blitzortung TOA Lightning Network",
    status: "planned",
    last_updated: new Date().toISOString(),
    variables: ["stroke_timestamp", "stroke_lat", "stroke_lon", "current_ka"],
  },
];

export const AboutTab: React.FC<AboutTabProps> = ({
  modelInfo,
  sourcesStatus,
  isLoading,
}) => {
  const displaySources = sourcesStatus.length > 0 ? sourcesStatus : DEFAULT_SOURCES;
  const optimalThresh = modelInfo?.optimal_threshold ?? OPTIMAL_THRESHOLD;
  const watchThresh = modelInfo?.alert_tiers?.watch ?? ALERT_THRESHOLD;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="border-b border-slate-200/60 pb-3 dark:border-slate-800/60">
        <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <Info className="h-5 w-5 text-teal-600 dark:text-teal-400" />
          About VajraNowcast
        </h2>
        <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
          AI-Powered Convective Weather Nowcasting Platform for India (v1.1.0)
        </p>
      </div>

      {/* Mandatory Disclaimer Alert */}
      <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-800 dark:text-amber-200 leading-relaxed">
        <div className="flex items-center gap-1.5 font-bold mb-1">
          <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0" />
          Experimental Model Notice
        </div>
        {DEFAULT_DISCLAIMER} This system is an academic &amp; technological demonstration and does not replace official bulletins from the India Meteorological Department (IMD) or State Disaster Management Authorities.
      </div>

      {/* What it predicts */}
      <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/60 space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-teal-600 dark:text-teal-400 flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5" /> What the Model Predicts
        </h3>
        <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
          The ML model produces the <strong>chance of heavy warm rain (&gt; 2 mm in the next hour)</strong>, used as a statistical thunderstorm proxy.
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
          Lead times beyond 1 hour (2h, 3h, 6h) use numerical weather forecast inputs and represent extrapolated convective threat horizons.
        </p>
      </div>

      {/* Decision Threshold & Severity Scale */}
      <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/60 space-y-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-teal-600 dark:text-teal-400 flex items-center gap-1.5">
          <Cpu className="h-3.5 w-3.5" /> Thresholds &amp; Decision Boundary
        </h3>
        <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
          Due to extreme natural class imbalance (~1.5% positive convective prevalence), standard 50% cutoffs fail. The statistical decision boundary is calibrated at:
        </p>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-xl bg-slate-100 p-2.5 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Optimal Storm Threshold</span>
            <strong className="text-sm font-bold text-slate-900 dark:text-white tabular-nums">
              P(TS) ≥ {optimalThresh.toFixed(3)}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2.5 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Operational Watch</span>
            <strong className="text-sm font-bold text-rose-600 dark:text-rose-400 tabular-nums">
              P(TS) ≥ {watchThresh.toFixed(2)}
            </strong>
          </div>
        </div>
      </div>

      {/* Meteorological Data Sources */}
      <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/60 space-y-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-teal-600 dark:text-teal-400 flex items-center gap-1.5">
          <Database className="h-3.5 w-3.5" /> Meteorological Data Feeds
        </h3>
        <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          Live data is fetched by your browser from Open-Meteo. Regional grids and city overviews are precomputed hourly.
        </p>
        <div className="space-y-1.5">
          {displaySources.map((src) => (
            <div
              key={src.source_name}
              className="flex items-center justify-between rounded-xl bg-slate-100/70 px-3 py-2 text-xs dark:bg-slate-800/50"
            >
              <span className="font-medium text-slate-800 dark:text-slate-200">{src.source_name}</span>
              <span
                className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                  src.status === "active"
                    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                    : "bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300"
                }`}
              >
                {src.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Attributions */}
      <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/60 space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-teal-600 dark:text-teal-400 flex items-center gap-1.5">
          <Layers className="h-3.5 w-3.5" /> Open Licenses &amp; Attributions
        </h3>
        <ul className="space-y-1 text-xs text-slate-600 dark:text-slate-300">
          {MAP_ATTRIBUTIONS.map((attr, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <span className="text-teal-500">•</span>
              <span>{attr}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
