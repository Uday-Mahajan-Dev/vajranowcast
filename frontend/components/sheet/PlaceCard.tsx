"use client";

import React, { useState } from "react";
import {
  NowcastResponse,
  ThunderstormPrediction,
  SeverityLevel,
} from "@/lib/types";
import {
  SEVERITY_CONFIG,
  DEFAULT_DISCLAIMER,
  getSeverityFromProbability,
} from "@/lib/constants";
import {
  formatProbability,
  formatISTTime,
  formatValidityWindow,
} from "@/lib/utils";
import {
  ArrowLeft,
  Share2,
  Check,
  Sparkles,
  Zap,
  Gauge,
  Thermometer,
  Droplets,
  Cloud,
  Wind,
  Layers,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  RotateCcw,
  Clock,
  Info,
  ShieldAlert,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
} from "recharts";
import { LeadTimeOption } from "../map/LeadTimeSlider";

interface PlaceCardProps {
  placeName: string;
  coordinates?: { lat: number; lon: number } | null;
  nowcastData?: NowcastResponse | null;
  isLoading: boolean;
  error?: string | null;
  selectedLead: LeadTimeOption;
  onSelectLead: (lead: LeadTimeOption) => void;
  onBack: () => void;
  onRetry: () => void;
}

export const PlaceCard: React.FC<PlaceCardProps> = ({
  placeName,
  coordinates,
  nowcastData,
  isLoading,
  error,
  selectedLead,
  onSelectLead,
  onBack,
  onRetry,
}) => {
  const [copied, setCopied] = useState(false);
  const [isWhyOpen, setIsWhyOpen] = useState(false);

  // Handle Share URL Copy
  const handleShare = () => {
    if (!coordinates) return;
    const url = new URL(window.location.href);
    url.searchParams.set("lat", coordinates.lat.toFixed(4));
    url.searchParams.set("lon", coordinates.lon.toFixed(4));
    navigator.clipboard.writeText(url.toString()).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  // Find prediction for selected lead (or fallback to first)
  const predictions = nowcastData?.predictions || [];
  const activePred: ThunderstormPrediction | undefined =
    predictions.find((p) => p.lead_time_hours === selectedLead) ||
    predictions[0];

  const sevKey = (activePred?.severity || "none") as SeverityLevel;
  const sevConfig = SEVERITY_CONFIG[sevKey] || SEVERITY_CONFIG.none;
  const conds = activePred?.input_conditions || {};

  // Forecast curve data for Recharts
  const chartData = predictions.map((p) => {
    const label = p.lead_time_hours === 0 ? "Now" : `+${p.lead_time_hours}h`;
    return {
      name: label,
      prob: p.thunderstorm_probability,
      lead: p.lead_time_hours,
      time: p.valid_from ? formatISTTime(p.valid_from, "timeOnly") : label,
      severity: p.severity,
    };
  });

  return (
    <div className="space-y-4">
      {/* 1. Header Bar with Back and Share */}
      <div className="flex items-center justify-between border-b border-slate-200/60 pb-3 dark:border-slate-800/60">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 rounded-xl px-2.5 py-1 text-xs font-semibold text-teal-600 transition-colors hover:bg-teal-500/10 dark:text-teal-400"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Overview</span>
        </button>

        <div className="flex items-center gap-2">
          {coordinates && (
            <span className="text-[11px] text-slate-400 font-mono">
              {coordinates.lat.toFixed(2)}°N, {coordinates.lon.toFixed(2)}°E
            </span>
          )}
          <button
            onClick={handleShare}
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-slate-200/60 bg-white/70 text-slate-600 shadow-xs hover:bg-slate-100 dark:border-slate-700/60 dark:bg-slate-800/70 dark:text-slate-300 dark:hover:bg-slate-700"
            title="Share Location"
          >
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Share2 className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* 2. Loading Skeleton State */}
      {isLoading && (
        <div className="space-y-4 animate-pulse">
          <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-5 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
            <div className="h-6 w-3/4 bg-slate-200 dark:bg-slate-800 rounded-lg mb-2" />
            <div className="h-4 w-1/2 bg-slate-200 dark:bg-slate-800 rounded-lg mb-4" />
            <div className="h-16 w-full bg-slate-200 dark:bg-slate-800 rounded-xl" />
          </div>
          <div className="h-28 w-full bg-slate-200 dark:bg-slate-800 rounded-2xl" />
          <div className="h-36 w-full bg-slate-200 dark:bg-slate-800 rounded-2xl" />
        </div>
      )}

      {/* 3. Error State with Retry */}
      {!isLoading && error && (
        <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-5 text-center shadow-sm">
          <AlertTriangle className="mx-auto h-8 w-8 text-rose-500 mb-2" />
          <h3 className="text-sm font-bold text-rose-900 dark:text-rose-200">
            Unable to Load Nowcast
          </h3>
          <p className="text-xs text-rose-700 dark:text-rose-300 mt-1 max-w-xs mx-auto">
            {error}
          </p>
          <button
            onClick={onRetry}
            className="mt-4 inline-flex items-center gap-1.5 rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-rose-700 transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>Retry Nowcast</span>
          </button>
        </div>
      )}

      {/* 4. Main Nowcast Card Content */}
      {!isLoading && !error && activePred && (
        <>
          {/* Hero Threat Banner */}
          <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-5 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-lg font-black text-slate-900 dark:text-white">
                  {placeName}
                </h2>
                <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  <Clock className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400" />
                  <span>
                    {activePred.valid_from && activePred.valid_until
                      ? formatValidityWindow(activePred.valid_from, activePred.valid_until)
                      : "1-Hour Forecast Window"}
                  </span>
                </div>
              </div>

              {/* Threat Severity Badge */}
              <div
                className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wider ${sevConfig.badgeClass}`}
              >
                {sevConfig.label}
              </div>
            </div>

            {/* Probability Metric Display */}
            <div className="mt-4 flex items-baseline justify-between rounded-xl bg-slate-100/80 p-3.5 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
              <div>
                <div className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                  Thunderstorm Probability
                </div>
                <div className="text-3xl font-black text-slate-900 dark:text-white mt-0.5">
                  {formatProbability(activePred.thunderstorm_probability)}
                </div>
              </div>

              <div className="text-right space-y-1">
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  Lightning: <span className="font-bold text-amber-500">{formatProbability(activePred.lightning_probability)}</span>
                </div>
                <div className="text-xs text-slate-500 dark:text-slate-400">
                  Confidence: <span className="font-bold text-teal-600 dark:text-teal-400">{Math.round(activePred.confidence * 100)}%</span>
                </div>
              </div>
            </div>

            {/* Extrapolated Lead Time Warning for lead >= 1 */}
            {activePred.lead_time_hours >= 1 && (
              <div className="mt-3 flex items-start gap-2 rounded-xl bg-amber-500/10 p-2.5 text-[11px] text-amber-800 dark:text-amber-300 border border-amber-500/20">
                <Info className="h-4 w-4 shrink-0 text-amber-500 mt-0.5" />
                <div>
                  <span className="font-bold">+{activePred.lead_time_hours}h Forecast: </span>
                  <span>{activePred.lead_time_note || "Extrapolated beyond training lead time (1h). Confidence decays with lead time."}</span>
                </div>
              </div>
            )}

            {/* Severe Storm & Lightning Safety Card (Warning Tier >= 60%) */}
            {activePred.thunderstorm_probability >= 0.60 && (
              <div className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-red-900 dark:text-red-200">
                <div className="flex items-center gap-1.5 text-xs font-black uppercase tracking-wider text-red-700 dark:text-red-400">
                  <ShieldAlert className="h-4 w-4" />
                  Severe Convective Storm Safety Actions
                </div>
                <ul className="mt-2 space-y-1.5 text-[11px] leading-relaxed text-red-800 dark:text-red-300">
                  <li className="flex items-start gap-1.5">
                    <span className="font-bold text-red-600 dark:text-red-400">• Lightning:</span>
                    <span>Move indoors immediately; avoid open fields, tall isolated trees, and metal poles.</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="font-bold text-red-600 dark:text-red-400">• Heavy Downpours:</span>
                    <span>Avoid low-lying underpasses and waterlogged roads prone to sudden flooding.</span>
                  </li>
                  <li className="flex items-start gap-1.5">
                    <span className="font-bold text-red-600 dark:text-red-400">• Strong Squalls:</span>
                    <span>Secure loose rooftop objects and park vehicles away from old trees/hoardings.</span>
                  </li>
                </ul>
              </div>
            )}
          </div>

          {/* 5. 6-Hour Strip (Horizontal Forecast Scroller) */}
          {predictions.length > 1 && (
            <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
              <div className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider mb-2.5">
                Hourly Forecast Timeline
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
                {predictions.map((p) => {
                  const isSelected = selectedLead === p.lead_time_hours;
                  const pSev = SEVERITY_CONFIG[p.severity as SeverityLevel] || SEVERITY_CONFIG.none;
                  const leadLabel = p.lead_time_hours === 0 ? "Now" : `+${p.lead_time_hours}h`;
                  const temp = p.input_conditions?.temperature_2m;

                  return (
                    <button
                      key={p.lead_time_hours}
                      onClick={() => onSelectLead(p.lead_time_hours as LeadTimeOption)}
                      className={`flex min-w-[70px] flex-col items-center justify-between rounded-xl p-2.5 text-center transition-all ${
                        isSelected
                          ? "bg-teal-600 text-white shadow-md shadow-teal-900/20 ring-2 ring-teal-500"
                          : "bg-slate-100/90 text-slate-700 hover:bg-slate-200 dark:bg-slate-800/80 dark:text-slate-300 dark:hover:bg-slate-700/80"
                      }`}
                    >
                      <span className="text-[11px] font-bold">{leadLabel}</span>
                      <span className="text-[10px] opacity-75">
                        {p.valid_from ? formatISTTime(p.valid_from, "timeOnly").replace(" IST", "") : ""}
                      </span>
                      <div
                        className={`my-1.5 rounded-full px-2 py-0.5 text-[11px] font-black ${
                          isSelected ? "bg-white/20 text-white" : pSev.chipClass
                        }`}
                      >
                        {formatProbability(p.thunderstorm_probability)}
                      </div>
                      <span className="text-[10px] font-medium">
                        {temp !== undefined ? `${temp.toFixed(0)}°C` : "--°"}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* 6. Hourly Probability Curve (Recharts) */}
          {chartData.length > 1 && (
            <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
                  Risk Curve
                </div>
                <div className="text-[11px] text-teal-600 dark:text-teal-400 font-semibold">
                  0.186 Alert Threshold
                </div>
              </div>

              <div className="h-36 w-full select-none">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={chartData}
                    margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="probGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#0d9488" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#0d9488" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 10, fill: "#94a3b8" }}
                      tickLine={false}
                    />
                    <YAxis
                      domain={[0, 1]}
                      tick={{ fontSize: 10, fill: "#94a3b8" }}
                      tickFormatter={(v) => `${Math.round(v * 100)}%`}
                      tickCount={4}
                    />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload || !payload.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="rounded-xl border border-slate-200 bg-white/95 p-2 shadow-xl backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/95 text-xs">
                            <div className="font-bold text-slate-900 dark:text-white">
                              {d.name} ({d.time})
                            </div>
                            <div className="text-teal-600 dark:text-teal-400 font-bold mt-0.5">
                              P(TS): {formatProbability(d.prob)}
                            </div>
                          </div>
                        );
                      }}
                    />
                    <ReferenceLine
                      y={0.186}
                      stroke="#0d9488"
                      strokeDasharray="4 4"
                      strokeWidth={1.5}
                    />
                    <Area
                      type="monotone"
                      dataKey="prob"
                      stroke="#0d9488"
                      strokeWidth={2.5}
                      fillOpacity={1}
                      fill="url(#probGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* 7. Surface Weather Metrics Grid */}
          <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
            <div className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider mb-3">
              Observed Surface Conditions
            </div>

            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
                <Thermometer className="mx-auto h-4 w-4 text-amber-500 mb-1" />
                <div className="text-[10px] text-slate-400">Temperature</div>
                <div className="font-bold text-slate-900 dark:text-white text-sm">
                  {conds.temperature_2m !== undefined ? `${conds.temperature_2m.toFixed(1)}°C` : "--°"}
                </div>
              </div>

              <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
                <Droplets className="mx-auto h-4 w-4 text-sky-500 mb-1" />
                <div className="text-[10px] text-slate-400">Humidity</div>
                <div className="font-bold text-slate-900 dark:text-white text-sm">
                  {conds.relative_humidity !== undefined ? `${conds.relative_humidity.toFixed(0)}%` : "--%"}
                </div>
              </div>

              <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
                <Cloud className="mx-auto h-4 w-4 text-slate-400 mb-1" />
                <div className="text-[10px] text-slate-400">Cloud Cover</div>
                <div className="font-bold text-slate-900 dark:text-white text-sm">
                  {conds.cloud_cover !== undefined ? `${conds.cloud_cover.toFixed(0)}%` : "--%"}
                </div>
              </div>

              <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
                <Wind className="mx-auto h-4 w-4 text-teal-500 mb-1" />
                <div className="text-[10px] text-slate-400">Wind Speed</div>
                <div className="font-bold text-slate-900 dark:text-white text-sm">
                  {conds.wind_speed_10m !== undefined ? `${conds.wind_speed_10m.toFixed(1)} km/h` : "--"}
                </div>
              </div>

              <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
                <Droplets className="mx-auto h-4 w-4 text-indigo-500 mb-1" />
                <div className="text-[10px] text-slate-400">Precip (1h ago)</div>
                <div className="font-bold text-slate-900 dark:text-white text-sm">
                  {conds.precip_1hr_ago !== undefined ? `${conds.precip_1hr_ago.toFixed(1)} mm` : "--"}
                </div>
              </div>

              <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
                <Gauge className="mx-auto h-4 w-4 text-purple-500 mb-1" />
                <div className="text-[10px] text-slate-400">Dew Pt Depr</div>
                <div className="font-bold text-slate-900 dark:text-white text-sm">
                  {conds.dew_point_depression !== undefined ? `${conds.dew_point_depression.toFixed(1)}°C` : "--"}
                </div>
              </div>
            </div>
          </div>

          {/* 8. Honest Collapsible "Why this estimate?" Section */}
          <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
            <button
              onClick={() => setIsWhyOpen(!isWhyOpen)}
              className="flex w-full items-center justify-between text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider"
            >
              <span className="flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-teal-600 dark:text-teal-400" />
                Why this estimate?
              </span>
              {isWhyOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>

            {isWhyOpen && (
              <div className="mt-3 space-y-2.5 text-xs text-slate-600 dark:text-slate-300 border-t border-slate-200/60 pt-3 dark:border-slate-800/60 animate-in fade-in-50 leading-relaxed">
                <div className="rounded-xl bg-slate-100/80 p-2.5 dark:bg-slate-800/60 font-medium text-slate-800 dark:text-slate-200">
                  <span className="font-bold text-teal-600 dark:text-teal-400">Target Predicted: </span>
                  Chance of heavy warm rain (&gt; 2 mm in the next hour), used as an operational thunderstorm proxy.
                </div>
                <div>
                  <span className="font-bold text-slate-900 dark:text-white">1. Recent Rainfall: </span>
                  <span>
                    Measured precipitation 1 hour ago ({conds.precip_1hr_ago !== undefined ? `${conds.precip_1hr_ago.toFixed(1)} mm` : "--"}) and past 3-hour precipitation trend.
                  </span>
                </div>
                <div>
                  <span className="font-bold text-slate-900 dark:text-white">2. Saturation & Moisture: </span>
                  <span>
                    Relative humidity ({conds.relative_humidity !== undefined ? `${conds.relative_humidity.toFixed(0)}%` : "--"}) and dew point depression ({conds.dew_point_depression !== undefined ? `${conds.dew_point_depression.toFixed(1)}°C` : "--"}) — measuring how close the surface air is to saturation.
                  </span>
                </div>
                <div>
                  <span className="font-bold text-slate-900 dark:text-white">3. Temperature & Trends: </span>
                  <span>
                    Surface temperature ({conds.temperature_2m !== undefined ? `${conds.temperature_2m.toFixed(1)}°C` : "--"}), cloud cover ({conds.cloud_cover !== undefined ? `${conds.cloud_cover.toFixed(0)}%` : "--"}), and 3-hour pressure/temperature trends.
                  </span>
                </div>
                <div>
                  <span className="font-bold text-slate-900 dark:text-white">4. Diurnal & Seasonal Timing: </span>
                  <span>
                    Time of day (solar heating cycle), calendar month, and geographic location coordinates.
                  </span>
                </div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400 pt-1">
                  Calibrated ML decision threshold is <span className="font-bold text-teal-600 dark:text-teal-400">18.6% (0.186)</span> due to natural convective class imbalance.
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* Model Disclaimer */}
      <div className="rounded-xl bg-slate-100/70 p-2.5 text-[11px] text-slate-500 dark:bg-slate-900/50 dark:text-slate-400 border border-slate-200/50 dark:border-slate-800/50">
        <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-300">
          <Sparkles className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400" />
          VajraNowcast v1.1.0
        </div>
        <p className="mt-0.5 leading-relaxed">{DEFAULT_DISCLAIMER}</p>
      </div>
    </div>
  );
};
