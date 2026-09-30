"use client";

import React from "react";
import { X, Layers, Flame, Dot, MapPin, Bell, Building } from "lucide-react";
import { MAP_STYLES, MapStyleId } from "@/lib/constants";

export interface MapLayerSettings {
  showHeatmap: boolean;
  showGridPoints: boolean;
  showCityPins: boolean;
  showAlertPins: boolean;
  show3DBuildings: boolean;
}

interface MapTypeModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentStyle: MapStyleId;
  onSelectStyle: (style: MapStyleId) => void;
  layers: MapLayerSettings;
  onToggleLayer: (layerKey: keyof MapLayerSettings) => void;
}

export const MapTypeModal: React.FC<MapTypeModalProps> = ({
  isOpen,
  onClose,
  currentStyle,
  onSelectStyle,
  layers,
  onToggleLayer,
}) => {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="map-layers-title"
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 backdrop-blur-sm sm:items-center sm:p-4 animate-in fade-in-50"
    >
      <div
        className="w-full max-w-md rounded-t-3xl sm:rounded-3xl glass-panel-elevated p-5 shadow-glass-elevated animate-in slide-in-from-bottom-6 sm:zoom-in-95"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200/60 pb-3 dark:border-slate-700/60">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-teal-500/15 text-teal-600 dark:text-teal-400">
              <Layers className="h-4 w-4" />
            </div>
            <div>
              <h2 id="map-layers-title" className="text-sm font-bold text-slate-900 dark:text-white">
                Map Types &amp; Layers
              </h2>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Customise base map and convective overlays
              </p>
            </div>
          </div>
          <button
            id="close-map-type-modal"
            aria-label="Close map layer settings"
            onClick={onClose}
            className="rounded-full p-1.5 text-slate-400 hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-800/60 dark:hover:text-slate-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* 3 Map Style Cards */}
        <div className="mt-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            Map Type
          </div>
          <div className="grid grid-cols-3 gap-2.5">
            {(["default", "dark", "satellite"] as MapStyleId[]).map((styleKey) => {
              const cfg = MAP_STYLES[styleKey];
              const isSelected = currentStyle === styleKey;
              return (
                <button
                  key={styleKey}
                  id={`style-btn-${styleKey}`}
                  onClick={() => onSelectStyle(styleKey)}
                  className={`group relative flex flex-col items-center rounded-2xl p-2 transition-all ${
                    isSelected
                      ? "ring-2 ring-teal-500 bg-teal-500/10 dark:bg-teal-500/15"
                      : "border border-slate-200 hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700 hover:bg-slate-100/50 dark:hover:bg-slate-800/40"
                  }`}
                >
                  {/* Thumbnail Representation */}
                  <div
                    className="relative mb-2 h-14 w-full overflow-hidden rounded-xl border border-slate-300/40 shadow-inner flex items-center justify-center dark:border-slate-700/50"
                    style={{ backgroundColor: cfg.previewColor }}
                  >
                    {styleKey === "default" && (
                      <div className="w-full h-full bg-gradient-to-br from-emerald-50 via-slate-100 to-sky-100 flex items-center justify-center">
                        <span className="text-[10px] font-bold text-slate-600">Light</span>
                      </div>
                    )}
                    {styleKey === "dark" && (
                      <div className="w-full h-full bg-gradient-to-br from-slate-900 via-slate-950 to-indigo-950 flex items-center justify-center">
                        <span className="text-[10px] font-bold text-slate-300">Dark</span>
                      </div>
                    )}
                    {styleKey === "satellite" && (
                      <div className="w-full h-full bg-gradient-to-br from-emerald-950 via-teal-900 to-cyan-950 flex items-center justify-center">
                        <span className="text-[10px] font-bold text-cyan-200">Satellite</span>
                      </div>
                    )}
                  </div>
                  <span
                    className={`text-xs font-semibold ${
                      isSelected
                        ? "text-teal-600 dark:text-teal-400"
                        : "text-slate-700 dark:text-slate-300"
                    }`}
                  >
                    {cfg.name.split(" ")[0]}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Overlay Layer Toggles */}
        <div className="mt-5 space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            Convective Overlays
          </div>

          <div className="space-y-1 rounded-2xl bg-slate-100/70 p-1.5 dark:bg-slate-900/60">
            {/* Heatmap Toggle */}
            <label className="flex items-center justify-between rounded-xl px-3 py-2 cursor-pointer transition-colors hover:bg-white/60 dark:hover:bg-slate-800/60">
              <div className="flex items-center gap-2.5">
                <Flame className="h-4 w-4 text-orange-500" />
                <div>
                  <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Risk Heatmap
                  </div>
                  <div className="text-[10px] text-slate-400">
                    Smoothed probability gradient across India
                  </div>
                </div>
              </div>
              <input
                id="toggle-heatmap"
                type="checkbox"
                checked={layers.showHeatmap}
                onChange={() => onToggleLayer("showHeatmap")}
                className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 dark:border-slate-700 dark:bg-slate-800"
              />
            </label>

            {/* Grid Points Toggle */}
            <label className="flex items-center justify-between rounded-xl px-3 py-2 cursor-pointer transition-colors hover:bg-white/60 dark:hover:bg-slate-800/60">
              <div className="flex items-center gap-2.5">
                <Dot className="h-5 w-5 text-teal-500" />
                <div>
                  <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Grid Risk Points
                  </div>
                  <div className="text-[10px] text-slate-400">
                    ~70 regional meteorological observation nodes
                  </div>
                </div>
              </div>
              <input
                id="toggle-grid-points"
                type="checkbox"
                checked={layers.showGridPoints}
                onChange={() => onToggleLayer("showGridPoints")}
                className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 dark:border-slate-700 dark:bg-slate-800"
              />
            </label>

            {/* City Pins Toggle */}
            <label className="flex items-center justify-between rounded-xl px-3 py-2 cursor-pointer transition-colors hover:bg-white/60 dark:hover:bg-slate-800/60">
              <div className="flex items-center gap-2.5">
                <MapPin className="h-4 w-4 text-cyan-500" />
                <div>
                  <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    City Hub Pins
                  </div>
                  <div className="text-[10px] text-slate-400">
                    10 major Indian metropolitan forecasts
                  </div>
                </div>
              </div>
              <input
                id="toggle-city-pins"
                type="checkbox"
                checked={layers.showCityPins}
                onChange={() => onToggleLayer("showCityPins")}
                className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 dark:border-slate-700 dark:bg-slate-800"
              />
            </label>

            {/* Active Alerts Toggle */}
            <label className="flex items-center justify-between rounded-xl px-3 py-2 cursor-pointer transition-colors hover:bg-white/60 dark:hover:bg-slate-800/60">
              <div className="flex items-center gap-2.5">
                <Bell className="h-4 w-4 text-rose-500" />
                <div>
                  <div className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Active Alert Rings
                  </div>
                  <div className="text-[10px] text-slate-400">
                    Pulsing warnings for severe threats (&gt; 60%)
                  </div>
                </div>
              </div>
              <input
                id="toggle-alert-rings"
                type="checkbox"
                checked={layers.showAlertPins}
                onChange={() => onToggleLayer("showAlertPins")}
                className="h-4 w-4 rounded border-slate-300 text-teal-600 focus:ring-teal-500 dark:border-slate-700 dark:bg-slate-800"
              />
            </label>
          </div>
        </div>
      </div>
    </div>
  );
};
