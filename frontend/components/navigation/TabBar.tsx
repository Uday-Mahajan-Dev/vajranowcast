"use client";

import React from "react";
import { Map, Building2, Bell, History, Info, ShieldAlert } from "lucide-react";

export type ActiveTab = "map" | "cities" | "alerts" | "replays" | "about" | "staff";

interface TabBarProps {
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  activeAlertCount?: number;
  isLoggedIn?: boolean;
}

export const TabBar: React.FC<TabBarProps> = ({
  activeTab,
  onTabChange,
  activeAlertCount = 0,
  isLoggedIn = false,
}) => {
  const tabs = [
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

  return (
    <nav
      id="mobile-bottom-tab-bar"
      aria-label="Main Navigation"
      className="fixed bottom-0 left-0 right-0 z-40 block border-t border-slate-200/70 bg-white/90 backdrop-blur-xl dark:border-slate-800/80 dark:bg-slate-950/90 md:hidden"
    >
      <div className="flex h-16 items-center justify-around px-2">
        {tabs.map((t) => {
          const Icon = t.icon;
          const isActive = activeTab === t.id;
          return (
            <button
              key={t.id}
              id={`tab-${t.id}`}
              onClick={() => onTabChange(t.id)}
              className={`relative flex flex-1 flex-col items-center justify-center py-1 transition-all ${
                isActive
                  ? "text-teal-600 dark:text-teal-400 font-semibold"
                  : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <div className="relative">
                <Icon className={`h-5 w-5 ${isActive ? "scale-110" : ""}`} />
                {t.badge && (
                  <span className="absolute -right-2 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white shadow-sm animate-pulse">
                    {t.badge}
                  </span>
                )}
              </div>
              <span className="mt-1 text-[11px] tracking-tight">{t.label}</span>
              {isActive && (
                <span className="absolute bottom-1 h-0.5 w-6 rounded-full bg-teal-600 dark:bg-teal-400" />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};
