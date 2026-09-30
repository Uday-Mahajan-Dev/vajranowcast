"use client";

import React from "react";
import { History, MapPin, ExternalLink, ShieldCheck, AlertCircle, RefreshCw, Calendar, CheckCircle2, XCircle } from "lucide-react";
import { HistoricalReplayEvent } from "@/lib/types";
import { DEFAULT_DISCLAIMER, OPTIMAL_THRESHOLD } from "@/lib/constants";
import { formatProbability } from "@/lib/utils";

interface ReplaysTabProps {
  replays: HistoricalReplayEvent[];
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
  onSelectReplay: (event: HistoricalReplayEvent) => void;
}

export const ReplaysTab: React.FC<ReplaysTabProps> = ({
  replays,
  isLoading,
  error,
  onRetry,
  onSelectReplay,
}) => {
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="border-b border-slate-200/60 pb-3 dark:border-slate-800/60">
        <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <History className="h-5 w-5 text-teal-600 dark:text-teal-400" />
          Historical Event Replays
        </h2>
        <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
          Certified Indian convective weather cases verified against Open-Meteo ERA5 historical archive
        </p>
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
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className="h-28 w-full animate-pulse rounded-2xl border border-slate-200/50 bg-slate-100/60 p-4 dark:border-slate-800/50 dark:bg-slate-900/40"
            />
          ))}
        </div>
      )}

      {/* Replays List */}
      {!isLoading && !error && replays.length > 0 && (
        <div className="space-y-3">
          {replays.map((event) => {
            const isHit = event.computed_verdict?.toLowerCase() === "hit";
            return (
              <div
                key={event.event_id}
                className="group rounded-2xl border border-slate-200/70 bg-white/70 p-4 shadow-sm transition-all hover:border-teal-500/40 hover:bg-white dark:border-slate-800/80 dark:bg-slate-900/60 dark:hover:bg-slate-900"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white group-hover:text-teal-600 dark:group-hover:text-teal-400 transition-colors">
                      {event.event_name}
                    </h3>
                    <div className="flex items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                      <span className="flex items-center gap-1">
                        <MapPin className="h-3 w-3 text-teal-600" />
                        {event.city}, {event.state}
                      </span>
                      <span>•</span>
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {event.date} ({event.hour_ist})
                      </span>
                    </div>
                  </div>

                  <span
                    className={`flex items-center gap-1 rounded-lg px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                      isHit
                        ? "bg-emerald-500/15 text-emerald-700 border border-emerald-500/30 dark:text-emerald-300"
                        : "bg-amber-500/15 text-amber-700 border border-amber-500/30 dark:text-amber-300"
                    }`}
                  >
                    {isHit ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <XCircle className="h-3 w-3" />
                    )}
                    {event.computed_verdict || "Evaluated"}
                  </span>
                </div>

                <p className="mt-2 text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                  {event.synoptic_summary}
                </p>

                <div className="mt-3 flex items-center justify-between border-t border-slate-200/50 pt-2 text-[11px] text-slate-400 dark:border-slate-800/60">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                      Threshold {OPTIMAL_THRESHOLD}
                    </span>
                    {!event.verified_by_human && (
                      <span className="text-[10px] text-slate-400">
                        Not yet human-verified
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3">
                    {event.source_url && (
                      <a
                        href={event.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                        title="View news source"
                      >
                        Source <ExternalLink className="h-2.5 w-2.5" />
                      </a>
                    )}
                    <button
                      onClick={() => onSelectReplay(event)}
                      className="font-semibold text-teal-600 dark:text-teal-400 hover:underline"
                    >
                      Replay Event →
                    </button>
                  </div>
                </div>
              </div>
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
