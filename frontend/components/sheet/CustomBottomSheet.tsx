"use client";

import React, { useRef, useState, useEffect, useCallback } from "react";

export type SnapLevel = "peek" | "half" | "full";

interface CustomBottomSheetProps {
  snapLevel: SnapLevel;
  onSnapChange: (snap: SnapLevel) => void;
  children: React.ReactNode;
  className?: string;
}

export const CustomBottomSheet: React.FC<CustomBottomSheetProps> = ({
  snapLevel,
  onSnapChange,
  children,
  className = "",
}) => {
  const isDraggingRef = useRef(false);
  const startYRef = useRef(0);
  const currentTranslateRef = useRef(0);
  const sheetRef = useRef<HTMLDivElement>(null);
  const [dragOffset, setDragOffset] = useState<number | null>(null);

  const handlePointerDown = (e: React.PointerEvent) => {
    isDraggingRef.current = true;
    startYRef.current = e.clientY;
    currentTranslateRef.current = dragOffset || 0;
    try {
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      // Ignore
    }
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDraggingRef.current) return;
    const deltaY = e.clientY - startYRef.current;
    setDragOffset(deltaY);
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (!isDraggingRef.current) return;
    isDraggingRef.current = false;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // Ignore
    }

    const deltaY = e.clientY - startYRef.current;
    setDragOffset(null);

    // Determine snap transition based on deltaY distance
    if (deltaY > 50) {
      // Dragged down
      if (snapLevel === "full") onSnapChange("half");
      else if (snapLevel === "half") onSnapChange("peek");
    } else if (deltaY < -50) {
      // Dragged up
      if (snapLevel === "peek") onSnapChange("half");
      else if (snapLevel === "half") onSnapChange("full");
    }
  };

  // Height styling for snaps
  const getHeightClass = () => {
    switch (snapLevel) {
      case "full":
        return "h-[88vh]";
      case "half":
        return "h-[54vh]";
      case "peek":
      default:
        return "h-[110px]";
    }
  };

  return (
    <div
      ref={sheetRef}
      id="mobile-bottom-sheet"
      className={`fixed bottom-16 left-0 right-0 z-30 flex flex-col rounded-t-[28px] border-t border-slate-200/80 bg-white/95 backdrop-blur-2xl shadow-glass-elevated transition-all duration-300 ease-out dark:border-slate-800/80 dark:bg-slate-950/95 pointer-events-auto ${getHeightClass()} ${className}`}
      style={{
        transform: dragOffset !== null ? `translateY(${Math.max(-80, Math.min(200, dragOffset))}px)` : undefined,
        touchAction: "pan-y",
      }}
    >
      {/* Drag Handle Bar */}
      <div
        className="mx-auto mt-2.5 h-6 w-full flex items-center justify-center cursor-grab active:cursor-grabbing touch-none select-none"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <div className="h-1.5 w-12 rounded-full bg-slate-300 dark:bg-slate-700" />
      </div>

      {/* Sheet Content */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 pt-1 scrollbar-thin">
        {children}
      </div>
    </div>
  );
};
