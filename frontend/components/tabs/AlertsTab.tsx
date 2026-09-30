"use client";

import React from "react";
import { Bell, ShieldAlert, ShieldCheck, Clock, MapPin, AlertCircle, RefreshCw, Zap } from "lucide-react";
import { AlertResponse } from "@/lib/types";
import { getSeverityFromProbability, DEFAULT_DISCLAIMER } from "@/lib/constants";
import { formatISTTime, formatValidityWindow, formatProbability } from "@/lib/utils";

interface AlertsTabProps {
  alerts: AlertResponse[];
  isLoading: boolean;
  error: string | null;
  lastCheckedTime?: Date;
  onRetry: () => void;
  onSelectAlertCity: (cityName: string, lat: number, lon: number) => void;
}

export const AlertsTab: React.FC<AlertsTabProps> = ({
  alerts,
  isLoading,
  error,
  lastCheckedTime,
  onRetry,
  onSelectAlertCity,
}) => {
  // Filter out any expired alerts where valid_until is past
  const validAlerts = React.useMemo(() => {
    const now = Date.now();
    return alerts.filter((a) => {
      if (!a.valid_until) return true;
      const validUntilTs = new Date(a.valid_until).getTime();
      return isNaN(validUntilTs) || validUntilTs >= now;
    });
  }, [alerts]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200/60 pb-3 dark:border-slate-800/60">
        <div>
          <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Bell className="h-5 w-5 text-rose-500" />
            Active Convective Alerts
          </h2>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 flex items-center gap-1">
            <Clock className="h-3 w-3" />
            Checked {formatISTTime(lastCheckedTime || new Date(), "timeOnly")} • Refreshes every 5m
          </p>
        </div>

        {validAlerts.length > 0 && (
          <span className="flex h-5 items-center justify-center rounded-full bg-rose-500 px-2 text-[11px] font-bold text-white shadow-sm animate-pulse">
            {validAlerts.length} Active
          </span>
        )}
      </div>

      {/* Error State */}
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
        <div className="space-y-3">
          {[1, 2].map((n) => (
            <div
              key={n}
              className="h-28 w-full animate-pulse rounded-2xl border border-slate-200/50 bg-slate-100/60 p-4 dark:border-slate-800/50 dark:bg-slate-900/40"
            />
          ))}
        </div>
      )}

      {/* Active Alerts List */}
      {!isLoading && !error && validAlerts.length > 0 && (
        <div className="space-y-3">
          {validAlerts.map((alert) => {
            const sevMeta = getSeverityFromProbability(alert.thunderstorm_probability);
            const tier = alert.tier || (alert.thunderstorm_probability >= 0.60 ? "warning" : alert.thunderstorm_probability >= 0.40 ? "advisory" : "watch");
            const isTest = alert.is_test || false;

            const cardBorderClass = isTest
              ? "border-amber-400/60 bg-amber-500/5 dark:bg-amber-950/20"
              : tier === "warning"
              ? "border-red-500/40 bg-red-500/5 dark:bg-red-950/20"
              : tier === "advisory"
              ? "border-orange-500/40 bg-orange-500/5 dark:bg-orange-950/20"
              : "border-yellow-500/40 bg-yellow-500/5 dark:bg-yellow-950/20";

            return (
              <div
                key={alert.alert_id}
                className={`rounded-2xl border p-4 shadow-sm transition-all hover:shadow-md ${cardBorderClass}`}
              >
                {/* Test / Drill Hazard Ribbon */}
                {isTest && (
                  <div className="mb-2.5 flex items-center gap-1.5 rounded-lg bg-test-striped px-2.5 py-1 text-white shadow-xs">
                    <span className="text-[10px] font-black uppercase tracking-wider">
                      TEST — drill, not a real alert
                    </span>
                  </div>
                )}

                <div className="flex items-start justify-between gap-2">
                  <div>
                    <button
                      onClick={() => onSelectAlertCity(alert.city, alert.latitude, alert.longitude)}
                      className="font-bold text-slate-900 dark:text-white hover:text-teal-600 dark:hover:text-teal-400 flex items-center gap-1.5 text-sm transition-colors text-left"
                    >
                      {tier === "warning" ? (
                        <Zap className="h-4 w-4 text-red-500 fill-red-500 shrink-0" />
                      ) : (
                        <MapPin className="h-4 w-4 text-rose-500 shrink-0" />
                      )}
                      <span>{alert.city}</span>
                      <span className="rounded-md bg-slate-200/80 dark:bg-slate-800 px-1.5 py-0.2 text-[9px] uppercase font-bold text-slate-700 dark:text-slate-300">
                        {tier.toUpperCase()}
                      </span>
                    </button>
                    <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                      Valid: {formatValidityWindow(alert.valid_from, alert.valid_until)}
                    </div>
                  </div>

                  <span
                    className={`rounded-lg px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${sevMeta.chipClass}`}
                  >
                    {sevMeta.label}
                  </span>
                </div>

                <p className="mt-2.5 text-xs text-slate-700 dark:text-slate-200 leading-relaxed font-medium">
                  {alert.message}
                </p>

                <div className="mt-3 flex items-center justify-between border-t border-slate-200/50 pt-2 text-[11px] text-slate-500 dark:border-slate-800/60 dark:text-slate-400">
                  <div className="flex items-center gap-3">
                    <span>P(TS): <strong>{formatProbability(alert.thunderstorm_probability)}</strong></span>
                    <span className="flex items-center gap-0.5">
                      <Zap className="h-3 w-3 text-amber-500" />
                      P(Lightning): <strong>{formatProbability(alert.lightning_probability)}</strong>
                    </span>
                  </div>
                  <button
                    onClick={() => onSelectAlertCity(alert.city, alert.latitude, alert.longitude)}
                    className="text-teal-600 dark:text-teal-400 font-semibold hover:underline"
                  >
                    View Map →
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && validAlerts.length === 0 && (
        <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/5 p-6 text-center">
          <ShieldCheck className="mx-auto h-8 w-8 text-emerald-500 mb-2" />
          <h3 className="text-sm font-bold text-slate-900 dark:text-white">
            No Active Alerts Right Now
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-xs mx-auto">
            All 10 monitored metropolitan hubs are currently below operational convective alert thresholds (P(TS) &lt; 30%).
          </p>
          <div className="mt-3 text-[11px] text-slate-400">
            Checked at {formatISTTime(lastCheckedTime || new Date(), "timeOnly")}
          </div>
        </div>
      )}

      <div className="rounded-xl bg-slate-100/70 p-2 text-[10px] text-slate-500 dark:bg-slate-900/50 dark:text-slate-400">
        {DEFAULT_DISCLAIMER}
      </div>
    </div>
  );
};
