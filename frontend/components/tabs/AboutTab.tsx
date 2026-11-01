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
  const advisoryThresh = modelInfo?.alert_tiers?.advisory ?? 0.40;
  const warningThresh = modelInfo?.alert_tiers?.warning ?? 0.60;

  const locCount = modelInfo?.locations_count ?? 54;
  const period = modelInfo?.period ?? "2019-01-01 to 2026-10-28";
  const trainSplit = modelInfo?.splits?.train ?? "2019-01-01 to 2023-12-31";
  const valSplit = modelInfo?.splits?.validation ?? "2024-01-01 to 2024-12-31";
  const testSplit = modelInfo?.splits?.test ?? "2025-01-01 to 2026-10-28";
  const testMetrics = modelInfo?.metrics?.optimal_threshold;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="border-b border-slate-200/60 pb-3 dark:border-slate-800/60">
        <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <Info className="h-5 w-5 text-teal-600 dark:text-teal-400" />
          About VajraNowcast
        </h2>
        <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 flex items-center gap-1.5">
          <span>AI-Powered Convective Weather Nowcasting Platform for India (v1.1.0)</span>
          <span className="inline-flex items-center rounded-full bg-teal-500/10 px-2 py-0.5 text-[10px] font-semibold text-teal-600 dark:text-teal-400 border border-teal-500/20">
            Model {modelInfo?.model_version ? modelInfo.model_version.toUpperCase() : "V2"}
          </span>
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

      {/* Model Overview & Dataset */}
      <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/60 space-y-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-teal-600 dark:text-teal-400 flex items-center gap-1.5">
          <Cpu className="h-3.5 w-3.5" /> Model Architecture &amp; Training Dataset
        </h3>
        <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
          VajraNowcast is powered by an isotonic-calibrated <strong>HistGradientBoostingClassifier (v2)</strong> trained on real Open-Meteo ERA5 hourly reanalysis across <strong>{locCount} meteorological locations</strong> spanning <strong>{period}</strong>.
        </p>
        <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
          Unlike legacy v1 which enforced an artificial temperature restriction (&gt;25 °C over 10 cities), Model v2 eliminates thermal cliffs and generalizes across both warm-season convective cells and cool-season / cyclonic rainfall bands down through 22–24 °C.
        </p>
        <div className="grid grid-cols-3 gap-2 pt-1 text-[11px]">
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Train Split</span>
            <strong className="text-slate-900 dark:text-white block font-mono text-[10px] truncate" title={trainSplit}>
              {trainSplit.split(" ")[0].slice(0, 4)}–{trainSplit.split(" ")[2]?.slice(0, 4) || "2023"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Validation Split</span>
            <strong className="text-slate-900 dark:text-white block font-mono text-[10px] truncate" title={valSplit}>
              {valSplit.split(" ")[0].slice(0, 4)}–{valSplit.split(" ")[2]?.slice(0, 4) || "2024"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Holdout Test</span>
            <strong className="text-slate-900 dark:text-white block font-mono text-[10px] truncate" title={testSplit}>
              {testSplit.split(" ")[0].slice(0, 4)}–{testSplit.split(" ")[2]?.slice(0, 4) || "2026"}
            </strong>
          </div>
        </div>
      </div>

      {/* Independent Test Metrics */}
      <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/60 space-y-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-teal-600 dark:text-teal-400 flex items-center gap-1.5">
          <Sparkles className="h-3.5 w-3.5" /> Test Set Performance (2025–2026 Holdout)
        </h3>
        <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          Evaluated on 863,730 unseen test hours across 54 stations with chronological time-based splitting:
        </p>
        <div className="grid grid-cols-4 gap-2 text-center text-xs">
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">ROC AUC</span>
            <strong className="text-xs font-bold text-teal-600 dark:text-teal-400 tabular-nums">
              {testMetrics?.roc_auc !== undefined ? testMetrics.roc_auc.toFixed(4) : "0.9476"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">PR AUC</span>
            <strong className="text-xs font-bold text-teal-600 dark:text-teal-400 tabular-nums">
              {testMetrics?.pr_auc !== undefined ? testMetrics.pr_auc.toFixed(4) : "0.2991"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Brier Score</span>
            <strong className="text-xs font-bold text-emerald-600 dark:text-emerald-400 tabular-nums">
              {testMetrics?.brier_score !== undefined ? testMetrics.brier_score.toFixed(4) : "0.0151"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">F1 Score</span>
            <strong className="text-xs font-bold text-teal-600 dark:text-teal-400 tabular-nums">
              {testMetrics?.f1 !== undefined ? testMetrics.f1.toFixed(4) : "0.3590"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Precision</span>
            <strong className="text-xs font-bold text-slate-800 dark:text-slate-200 tabular-nums">
              {testMetrics?.precision !== undefined ? testMetrics.precision.toFixed(4) : "0.2886"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Recall (POD)</span>
            <strong className="text-xs font-bold text-slate-800 dark:text-slate-200 tabular-nums">
              {testMetrics?.recall_pod !== undefined ? testMetrics.recall_pod.toFixed(4) : "0.4749"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">CSI</span>
            <strong className="text-xs font-bold text-slate-800 dark:text-slate-200 tabular-nums">
              {testMetrics?.csi !== undefined ? testMetrics.csi.toFixed(4) : "0.2188"}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Optimal Thresh</span>
            <strong className="text-xs font-bold text-teal-600 dark:text-teal-400 tabular-nums">
              {optimalThresh.toFixed(4)}
            </strong>
          </div>
        </div>
      </div>

      {/* Severe Weather Signals */}
      <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/60 space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400 flex items-center gap-1.5">
          <ShieldAlert className="h-3.5 w-3.5" /> Severe Weather Signals
        </h3>
        <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
          Alert levels combine the ML thunderstorm probability with severe-weather signals from the forecast (thunderstorm codes, rain rate, wind and pressure trends).
        </p>
      </div>

      {/* Decision Threshold & Severity Scale */}
      <div className="rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/60 space-y-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-teal-600 dark:text-teal-400 flex items-center gap-1.5">
          <Cpu className="h-3.5 w-3.5" /> Operational Alert Tiers
        </h3>
        <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
          Calibrated to account for convective class imbalance (~1.8% positive prevalence) across India:
        </p>
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="rounded-xl bg-slate-100 p-2.5 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Watch Tier</span>
            <strong className="text-sm font-bold text-amber-600 dark:text-amber-400 tabular-nums">
              P(TS) ≥ {watchThresh.toFixed(2)}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2.5 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Advisory Tier</span>
            <strong className="text-sm font-bold text-orange-600 dark:text-orange-400 tabular-nums">
              P(TS) ≥ {advisoryThresh.toFixed(2)}
            </strong>
          </div>
          <div className="rounded-xl bg-slate-100 p-2.5 dark:bg-slate-800/60">
            <span className="text-[10px] text-slate-400 block font-medium">Warning Tier</span>
            <strong className="text-sm font-bold text-rose-600 dark:text-rose-400 tabular-nums">
              P(TS) ≥ {warningThresh.toFixed(2)}
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
