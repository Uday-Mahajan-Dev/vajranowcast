"use client";

import React from "react";
import {
  Map,
  Building2,
  Bell,
  History,
  Info,
  ShieldAlert,
  Sun,
  Moon,
  Laptop,
} from "lucide-react";
import { Logo } from "../brand/Logo";
import { ActiveTab } from "./TabBar";

interface NavigationRailProps {
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  activeAlertCount?: number;
  isLoggedIn?: boolean;
  theme: "light" | "dark" | "system";
  onThemeChange: (theme: "light" | "dark" | "system") => void;
  className?: string;
}

export const NavigationRail: React.FC<NavigationRailProps> = ({
  activeTab,
  onTabChange,
  activeAlertCount = 0,
  isLoggedIn = false,
  theme,
  onThemeChange,
  className = "",
}) => {
  const navItems = [
    { id: "map" as ActiveTab, label: "Map", icon: Map },
    { id: "cities" as ActiveTab, label: "Cities", icon: Building2 },
    {
      id: "alerts" as ActiveTab,
      label: "Alerts",
      icon: Bell,
      badge: activeAlertCount > 0 ? activeAlertCount : null,
    },
    { id: "replays" as ActiveTab, label: "Replays", icon: History },
    { id: "about" as ActiveTab, label: "About", icon: Info },
    ...(isLoggedIn
      ? [{ id: "staff" as ActiveTab, label: "Staff", icon: ShieldAlert }]
      : []),
  ];

  const cycleTheme = () => {
    if (theme === "light") onThemeChange("dark");
    else if (theme === "dark") onThemeChange("system");
    else onThemeChange("light");
  };

  return (
    <aside
      id="desktop-navigation-rail"
      aria-label="Desktop Navigation Rail"
      className={`fixed left-0 top-0 bottom-0 z-40 hidden w-20 flex-col items-center justify-between border-r border-slate-200/70 bg-white/90 py-5 backdrop-blur-xl dark:border-slate-800/80 dark:bg-slate-950/90 lg:flex ${className}`}
    >
      {/* Top Brand Logo */}
      <div className="flex flex-col items-center">
        <button
          onClick={() => onTabChange("map")}
          className="rounded-2xl p-1.5 transition-transform hover:scale-105 active:scale-95"
          title="VajraNowcast Home"
        >
          <Logo size="md" showText={false} />
        </button>
      </div>

      {/* Middle Navigation Icons */}
      <nav className="flex flex-col items-center gap-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              id={`rail-btn-${item.id}`}
              onClick={() => onTabChange(item.id)}
              className={`group relative flex h-13 w-13 flex-col items-center justify-center rounded-2xl p-2 transition-all ${
                isActive
                  ? "bg-teal-500/15 text-teal-600 dark:bg-teal-500/20 dark:text-teal-400 font-semibold"
                  : "text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-100"
              }`}
              title={item.label}
            >
              <div className="relative">
                <Icon className={`h-5 w-5 transition-transform ${isActive ? "scale-110" : "group-hover:scale-110"}`} />
                {item.badge && (
                  <span className="absolute -right-2.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white shadow-sm animate-pulse">
                    {item.badge}
                  </span>
                )}
              </div>
              <span className="mt-1 text-[10px] tracking-tight">{item.label}</span>
              {isActive && (
                <span className="absolute left-0 top-3 bottom-3 w-1 rounded-r-full bg-teal-600 dark:bg-teal-400" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom Theme Switcher */}
      <div className="flex flex-col items-center gap-2">
        <button
          id="btn-theme-switcher"
          onClick={cycleTheme}
          className="flex h-10 w-10 items-center justify-center rounded-xl text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-100"
          title={`Theme: ${theme.toUpperCase()} (Click to toggle)`}
          aria-label={`Current theme: ${theme}. Click to switch theme.`}
        >
          {theme === "light" && <Sun className="h-4 w-4 text-amber-500" />}
          {theme === "dark" && <Moon className="h-4 w-4 text-cyan-400" />}
          {theme === "system" && <Laptop className="h-4 w-4 text-slate-400" />}
        </button>
      </div>
    </aside>
  );
};
