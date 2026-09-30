"use client";

import React, { useState } from "react";
import { ChevronUp, ChevronDown, Flame, Layers } from "lucide-react";
import { SEVERITY_CONFIG } from "@/lib/constants";
import { SeverityLevel } from "@/lib/types";

interface MapLegendProps {
  showHeatmap: boolean;
  className?: string;
}

export const MapLegend: React.FC<MapLegendProps> = ({
  showHeatmap,
  className = "",
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div
      className={`fixed bottom-20 right-3.5 z-30 select-none lg:bottom-4 lg:right-5 ${className}`}
    >
      <div className="rounded-2xl glass-panel-elevated p-2 shadow-glass transition-all max-w-[270px]">
        {/* Toggle Button */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex w-full items-center justify-between gap-2 px-1 text-xs font-bold text-slate-800 dark:text-slate-100"
          aria-expanded={isExpanded}
          aria-label="Toggle severity and tier legend"
        >
          <div className="flex items-center gap-1.5">
            <span className="flex h-2 w-2 rounded-full bg-teal-500 animate-pulse" />
            <span>Alert &amp; Risk Legend</span>
          </div>
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronUp className="h-4 w-4 text-slate-400" />
          )}
        </button>

        {/* Collapsed Mini Ramp */}
        {!isExpanded && (
          <div className="mt-1.5 flex h-2 w-full overflow-hidden rounded-full">
            <div className="flex-1 bg-slate-500" title="Background (< 30%)" />
            <div className="flex-1 bg-yellow-500" title="Watch (30–40%)" />
            <div className="flex-1 bg-orange-500" title="Advisory (40–60%)" />
            <div className="flex-1 bg-red-500" title="Warning (≥ 60%)" />
          </div>
        )}

        {/* Expanded Detailed Scale */}
        {isExpanded && (
          <div className="mt-2 space-y-2 border-t border-slate-200/60 pt-2 text-[11px] dark:border-slate-800/60">
            {/* Operational Alert Tiers */}
            <div className="space-y-1.5">
              <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                Operational Alert Tiers
              </div>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-500 shadow-xs" />
                  <span className="font-bold text-red-600 dark:text-red-400">Warning</span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">≥ 60% (Severe)</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-orange-500 shadow-xs" />
                  <span className="font-bold text-orange-600 dark:text-orange-400">Advisory</span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">40–60% (Heavy Rain)</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-yellow-500 shadow-xs" />
                  <span className="font-bold text-yellow-600 dark:text-yellow-400">Watch</span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">30–40% (Developing)</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-slate-500 shadow-xs" />
                  <span className="font-medium text-slate-600 dark:text-slate-400">Low Risk</span>
                </div>
                <span className="text-[10px] text-slate-400 font-mono">&lt; 30%</span>
              </div>
            </div>

            {/* Decision Threshold Note */}
            <div className="rounded-lg bg-slate-100/80 dark:bg-slate-800/60 p-1.5 text-[10px] text-slate-500 dark:text-slate-400">
              <span className="font-bold text-teal-600 dark:text-teal-400">P(TS) ≥ 18.6%</span> ML statistical decision boundary for convective hit vs miss.
            </div>

            {/* Heatmap & Resolution Footnote */}
            <div className="border-t border-slate-200/50 pt-1.5 text-[10px] text-slate-400 leading-tight">
              {showHeatmap && (
                <div className="mb-1 text-orange-500 dark:text-orange-400 font-medium">
                  • Spatial grid: ~70 points (~175 km spacing)
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
