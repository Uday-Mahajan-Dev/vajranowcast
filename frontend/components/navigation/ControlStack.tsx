"use client";

import React, { useState } from "react";
import { Layers, Navigation, Compass, Plus, Minus, Loader2 } from "lucide-react";

interface ControlStackProps {
  onOpenLayers: () => void;
  onLocateMe: () => void;
  onResetNorth: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  bearing?: number;
  pitch?: number;
  isLocating?: boolean;
  className?: string;
}

export const ControlStack: React.FC<ControlStackProps> = ({
  onOpenLayers,
  onLocateMe,
  onResetNorth,
  onZoomIn,
  onZoomOut,
  bearing = 0,
  pitch = 0,
  isLocating = false,
  className = "",
}) => {
  const isRotated = Math.abs(bearing) > 0.5 || Math.abs(pitch) > 0.5;

  return (
    <div
      className={`fixed right-3.5 top-20 z-20 flex flex-col gap-2 select-none md:right-5 md:top-24 ${className}`}
    >
      {/* Upper Group: Layers & Geolocation */}
      <div className="flex flex-col rounded-2xl glass-panel-elevated p-1 shadow-glass">
        <button
          id="btn-map-layers"
          aria-label="Change map type and layer overlays"
          title="Map Types & Layers"
          onClick={onOpenLayers}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-slate-700 transition-colors hover:bg-slate-200/60 hover:text-teal-600 dark:text-slate-200 dark:hover:bg-slate-800/80 dark:hover:text-teal-400"
        >
          <Layers className="h-5 w-5" />
        </button>

        <div className="my-0.5 h-px bg-slate-200/60 dark:bg-slate-700/60" />

        <button
          id="btn-locate-me"
          aria-label="Locate my position in India"
          title="Locate Me (GPS)"
          onClick={onLocateMe}
          disabled={isLocating}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-slate-700 transition-colors hover:bg-slate-200/60 hover:text-cyan-600 dark:text-slate-200 dark:hover:bg-slate-800/80 dark:hover:text-cyan-400"
        >
          {isLocating ? (
            <Loader2 className="h-5 w-5 animate-spin text-cyan-500" />
          ) : (
            <Navigation className="h-5 w-5" />
          )}
        </button>
      </div>

      {/* Compass / Reset North (Visual Indicator & Reset) */}
      <div className="flex flex-col rounded-2xl glass-panel-elevated p-1 shadow-glass">
        <button
          id="btn-compass-north"
          aria-label={`Compass needle: bearing ${Math.round(bearing)} degrees. Click to reset north.`}
          title={isRotated ? "Reset view to North" : "Pointing North"}
          onClick={onResetNorth}
          className={`flex h-11 w-11 items-center justify-center rounded-xl transition-all ${
            isRotated
              ? "text-rose-500 hover:bg-rose-500/10 dark:text-rose-400"
              : "text-slate-400 hover:bg-slate-200/60 dark:text-slate-500 dark:hover:bg-slate-800/80"
          }`}
        >
          <div
            className="transition-transform duration-200"
            style={{ transform: `rotate(${-bearing}deg)` }}
          >
            <Compass className="h-5 w-5" />
          </div>
        </button>
      </div>

      {/* Desktop Zoom Stack (+ / -) */}
      <div className="hidden flex-col rounded-2xl glass-panel-elevated p-1 shadow-glass md:flex">
        <button
          id="btn-zoom-in"
          aria-label="Zoom in on map"
          title="Zoom In"
          onClick={onZoomIn}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-slate-700 transition-colors hover:bg-slate-200/60 hover:text-teal-600 dark:text-slate-200 dark:hover:bg-slate-800/80 dark:hover:text-teal-400"
        >
          <Plus className="h-5 w-5" />
        </button>

        <div className="my-0.5 h-px bg-slate-200/60 dark:bg-slate-700/60" />

        <button
          id="btn-zoom-out"
          aria-label="Zoom out of map"
          title="Zoom Out"
          onClick={onZoomOut}
          className="flex h-11 w-11 items-center justify-center rounded-xl text-slate-700 transition-colors hover:bg-slate-200/60 hover:text-teal-600 dark:text-slate-200 dark:hover:bg-slate-800/80 dark:hover:text-teal-400"
        >
          <Minus className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
};
