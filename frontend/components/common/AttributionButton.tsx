"use client";

import React, { useState } from "react";
import { Info, X, ExternalLink, ShieldCheck } from "lucide-react";
import { DEFAULT_DISCLAIMER, MAP_ATTRIBUTIONS } from "@/lib/constants";

interface AttributionButtonProps {
  currentStyle?: string;
  className?: string;
}

export const AttributionButton: React.FC<AttributionButtonProps> = ({
  currentStyle = "default",
  className = "",
}) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className={`fixed bottom-20 left-3 z-30 lg:bottom-4 lg:left-24 select-none ${className}`}>
      {/* Collapsed Button */}
      {!isOpen && (
        <button
          id="btn-map-attribution"
          aria-label="Map data attributions and model disclaimer"
          title="Map & Weather Data Attribution"
          onClick={() => setIsOpen(true)}
          className="flex h-7 items-center gap-1.5 rounded-full glass-panel px-2.5 text-[11px] font-medium text-slate-600 shadow-sm transition-all hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-slate-800/80"
        >
          <Info className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400" />
          <span className="hidden sm:inline">Attribution & Disclaimer</span>
          <span className="sm:hidden">ⓘ</span>
        </button>
      )}

      {/* Expanded Modal / Popover */}
      {isOpen && (
        <div className="w-80 max-w-[calc(100vw-24px)] rounded-2xl glass-panel-elevated p-4 shadow-glass-elevated animate-in fade-in-50 zoom-in-95">
          <div className="flex items-center justify-between border-b border-slate-200/60 pb-2.5 dark:border-slate-700/60">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-800 dark:text-slate-100">
              <ShieldCheck className="h-4 w-4 text-teal-600 dark:text-teal-400" />
              <span>Data Sources & Attribution</span>
            </div>
            <button
              aria-label="Close attribution window"
              onClick={() => setIsOpen(false)}
              className="rounded-full p-1 text-slate-400 hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-800/60 dark:hover:text-slate-200"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="mt-3 space-y-2 text-xs text-slate-600 dark:text-slate-300">
            <div className="rounded-xl bg-amber-500/10 p-2.5 text-[11px] text-amber-700 dark:text-amber-300 border border-amber-500/20">
              <strong>Mandatory Notice:</strong> {DEFAULT_DISCLAIMER}
            </div>

            <ul className="space-y-1.5 pl-1 pt-1 text-[11px]">
              <li className="flex items-start gap-1.5">
                <span className="text-teal-500">•</span>
                <span>
                  <strong>Map Vectors:</strong> OpenFreeMap &amp; OpenStreetMap contributors (ODbL).
                </span>
              </li>
              {currentStyle === "satellite" && (
                <li className="flex items-start gap-1.5">
                  <span className="text-teal-500">•</span>
                  <span>
                    <strong>Satellite Imagery:</strong> EOX Sentinel-2 cloudless (s2maps.eu by EOX IT Services GmbH, CC BY-NC-SA 4.0).
                  </span>
                </li>
              )}
              <li className="flex items-start gap-1.5">
                <span className="text-teal-500">•</span>
                <span>
                  <strong>Place Names:</strong> GeoNames (CC BY 4.0).
                </span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-teal-500">•</span>
                <span>
                  <strong>Atmospheric NWP &amp; Geocoding:</strong> Open-Meteo (CC BY 4.0).
                </span>
              </li>
              <li className="flex items-start gap-1.5">
                <span className="text-teal-500">•</span>
                <span>
                  <strong>AI Engine:</strong> VajraNowcast v1.1.0 Calibrated Gradient Boosting Ensemble.
                </span>
              </li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
};
