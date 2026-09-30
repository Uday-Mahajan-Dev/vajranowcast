"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { Search, X, MapPin, Clock, User, Loader2, Sparkles, Building2 } from "lucide-react";
import { Logo } from "../brand/Logo";
import { searchIndianPlaces } from "@/lib/api";
import { INDIAN_CITIES } from "@/lib/constants";
import { searchPlacesIndex, loadIndiaPlaces, PlaceMatch } from "@/lib/places";
import { calculateDistanceKm } from "@/lib/utils";

export interface PlaceSelection {
  name: string;
  lat: number;
  lon: number;
  state?: string;
  admin1?: string;
  isHub?: boolean;
}

export interface SearchBarProps {
  onSelectPlace: (place: PlaceSelection) => void;
  onOpenAuth?: () => void;
  isLoggedIn?: boolean;
  userEmail?: string | null;
  placeholder?: string;
  variant?: "floating" | "inline" | "citiesTab";
  className?: string;
  autoFocus?: boolean;
}

const RECENT_SEARCHES_KEY = "vajranowcast_recent_places_v1";

interface MergedSuggestion {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
  isHub: boolean;
}

function isTopHubCity(name: string, state?: string): boolean {
  const norm = name.toLowerCase().trim();
  return INDIAN_CITIES.some(
    (c) => c.name.toLowerCase() === norm || norm.startsWith(c.name.toLowerCase())
  );
}

export const SearchBar: React.FC<SearchBarProps> = ({
  onSelectPlace,
  onOpenAuth,
  isLoggedIn = false,
  userEmail = null,
  placeholder = "Search city, town or district in India…",
  variant = "floating",
  className = "",
  autoFocus = false,
}) => {
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [geoMatches, setGeoMatches] = useState<MergedSuggestion[]>([]);
  const [apiResults, setApiResults] = useState<MergedSuggestion[]>([]);
  const [recentSearches, setRecentSearches] = useState<PlaceSelection[]>([]);
  const [activeIndex, setActiveIndex] = useState<number>(-1);

  const searchContainerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const listboxRef = useRef<HTMLDivElement>(null);

  // 1. Load recent searches from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem(RECENT_SEARCHES_KEY);
      if (saved) {
        setRecentSearches(JSON.parse(saved).slice(0, 5));
      }
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  const saveRecentSearch = useCallback((place: PlaceSelection) => {
    try {
      setRecentSearches((prev) => {
        const updated = [
          place,
          ...prev.filter(
            (p) => calculateDistanceKm(p.lat, p.lon, place.lat, place.lon) > 5 && p.name !== place.name
          ),
        ].slice(0, 5);
        try {
          localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(updated));
        } catch {
          // Ignore
        }
        return updated;
      });
    } catch {
      // Ignore
    }
  }, []);

  const clearRecentSearches = (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      localStorage.removeItem(RECENT_SEARCHES_KEY);
      setRecentSearches([]);
    } catch {
      // Ignore
    }
  };

  // 2. Instant matches from lazy-loaded GeoNames India index
  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setGeoMatches([]);
      return;
    }

    let isMounted = true;
    searchPlacesIndex(trimmed, 8).then((matches) => {
      if (isMounted) {
        setGeoMatches(
          matches.map((m) => ({
            id: m.id,
            name: m.name,
            state: m.state,
            lat: m.lat,
            lon: m.lon,
            isHub: m.isHub,
          }))
        );
      }
    });

    return () => {
      isMounted = false;
    };
  }, [query]);

  // 3. Debounced Open-Meteo Geocoding API fetch (250 ms, min 2 chars)
  useEffect(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setApiResults([]);
      setIsLoading(false);
      setActiveIndex(-1);
      return;
    }

    setIsLoading(true);
    debounceTimerRef.current = setTimeout(async () => {
      try {
        const geoResults = await searchIndianPlaces(trimmed);
        const mapped: MergedSuggestion[] = geoResults.map((r) => ({
          id: `api-${r.id}-${r.latitude}-${r.longitude}`,
          name: r.name,
          state: [r.admin1, r.country].filter(Boolean).join(", ") || "India",
          lat: r.latitude,
          lon: r.longitude,
          isHub: isTopHubCity(r.name, r.admin1),
        }));
        setApiResults(mapped);
      } catch (err) {
        console.warn("Geocoding fetch error:", err);
        setApiResults([]);
      } finally {
        setIsLoading(false);
      }
    }, 250);

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [query]);

  // 4. Merge, De-duplicate, and cap at max 8 suggestions
  const mergedSuggestions = useMemo<MergedSuggestion[]>(() => {
    const list: MergedSuggestion[] = [...geoMatches];

    // Add API results if not closely matching an existing suggestion
    for (const apiItem of apiResults) {
      const isDuplicate = list.some(
        (item) =>
          calculateDistanceKm(item.lat, item.lon, apiItem.lat, apiItem.lon) < 15 ||
          (item.name.toLowerCase() === apiItem.name.toLowerCase() &&
            item.state.toLowerCase() === apiItem.state.toLowerCase())
      );
      if (!isDuplicate) {
        list.push(apiItem);
      }
      if (list.length >= 8) break;
    }

    return list.slice(0, 8);
  }, [geoMatches, apiResults]);

  // Reset active keyboard highlight on suggestions change
  useEffect(() => {
    setActiveIndex(-1);
  }, [mergedSuggestions]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
        setActiveIndex(-1);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSelect = useCallback(
    (place: { name: string; lat: number; lon: number; state?: string }) => {
      setQuery(place.name);
      setIsOpen(false);
      setActiveIndex(-1);
      const sel: PlaceSelection = {
        name: place.name,
        lat: place.lat,
        lon: place.lon,
        state: place.state,
        admin1: place.state,
        isHub: isTopHubCity(place.name, place.state),
      };
      saveRecentSearch(sel);
      onSelectPlace(sel);
    },
    [onSelectPlace, saveRecentSearch]
  );

  // Keyboard navigation handler for combobox
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      setIsOpen(true);
      return;
    }

    const isShowingSuggestions = query.trim().length >= 2 && mergedSuggestions.length > 0;
    const isShowingRecent = query.trim().length < 2 && recentSearches.length > 0;
    const totalItems = isShowingSuggestions
      ? mergedSuggestions.length
      : isShowingRecent
      ? recentSearches.length
      : 0;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (totalItems === 0) return;
      setActiveIndex((prev) => (prev < totalItems - 1 ? prev + 1 : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (totalItems === 0) return;
      setActiveIndex((prev) => (prev > 0 ? prev - 1 : totalItems - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (isShowingSuggestions) {
        if (activeIndex >= 0 && mergedSuggestions[activeIndex]) {
          handleSelect(mergedSuggestions[activeIndex]);
        } else if (mergedSuggestions.length > 0) {
          handleSelect(mergedSuggestions[0]);
        }
      } else if (isShowingRecent) {
        if (activeIndex >= 0 && recentSearches[activeIndex]) {
          handleSelect(recentSearches[activeIndex]);
        }
      }
    } else if (e.key === "Escape") {
      setIsOpen(false);
      setActiveIndex(-1);
      inputRef.current?.blur();
    }
  };

  // Helper to render matched query string in bold
  const renderHighlightedName = (name: string, search: string) => {
    const trimmed = search.trim();
    if (!trimmed) return <span>{name}</span>;

    const lowerName = name.toLowerCase();
    const lowerSearch = trimmed.toLowerCase();
    const matchIdx = lowerName.indexOf(lowerSearch);

    if (matchIdx === -1) {
      return <span>{name}</span>;
    }

    const before = name.slice(0, matchIdx);
    const match = name.slice(matchIdx, matchIdx + trimmed.length);
    const after = name.slice(matchIdx + trimmed.length);

    return (
      <span>
        {before}
        <strong className="font-extrabold text-teal-600 dark:text-teal-400 underline decoration-teal-500/40 underline-offset-2">
          {match}
        </strong>
        {after}
      </span>
    );
  };

  const isCitiesTab = variant === "citiesTab";
  const isInline = variant === "inline" || isCitiesTab;

  return (
    <div
      ref={searchContainerRef}
      className={`relative z-30 w-full ${isInline ? "max-w-full" : "max-w-md"} ${className}`}
    >
      {/* Search Input Box */}
      <div
        className={`flex items-center gap-2 rounded-2xl transition-all duration-200 ${
          isCitiesTab
            ? "border border-slate-200/80 bg-slate-100/80 px-3.5 py-2.5 shadow-xs focus-within:border-teal-500 focus-within:bg-white focus-within:ring-2 focus-within:ring-teal-500/30 dark:border-slate-800 dark:bg-slate-900/80 dark:focus-within:bg-slate-900"
            : "glass-panel-elevated px-3.5 py-2.5 shadow-glass hover:shadow-glass-elevated focus-within:ring-2 focus-within:ring-teal-500/40"
        }`}
      >
        {!isCitiesTab && <Logo size="sm" showText={false} />}
        {isCitiesTab && (
          <Search className="h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" />
        )}

        <div className="relative flex flex-1 items-center">
          <input
            ref={inputRef}
            id={isCitiesTab ? "cities-tab-place-search-input" : "main-place-search-input"}
            type="text"
            role="combobox"
            aria-expanded={isOpen}
            aria-autocomplete="list"
            aria-controls="place-search-suggestions-list"
            aria-activedescendant={
              activeIndex >= 0 ? `place-suggestion-${activeIndex}` : undefined
            }
            autoFocus={autoFocus}
            placeholder={placeholder}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setIsOpen(true);
            }}
            onFocus={() => {
              setIsOpen(true);
              loadIndiaPlaces(); // Warm up lazy loader
            }}
            onKeyDown={handleKeyDown}
            className="w-full bg-transparent text-sm font-medium text-slate-900 placeholder:text-slate-400 focus:outline-none dark:text-white dark:placeholder:text-slate-500"
          />

          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-teal-600 dark:text-teal-400" />
          ) : query ? (
            <button
              aria-label="Clear search query"
              onClick={() => {
                setQuery("");
                setApiResults([]);
                setGeoMatches([]);
                setActiveIndex(-1);
                inputRef.current?.focus();
              }}
              className="rounded-full p-1 text-slate-400 hover:bg-slate-200/50 hover:text-slate-600 dark:hover:bg-slate-700/50 dark:hover:text-slate-200"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : !isCitiesTab ? (
            <Search className="h-4 w-4 text-slate-400" />
          ) : null}
        </div>

        {!isCitiesTab && (
          <>
            <div className="h-5 w-px bg-slate-300/60 dark:bg-slate-700/60" />
            {/* Profile / Auth Button */}
            <button
              id="profile-auth-button"
              aria-label={isLoggedIn ? `Account (${userEmail || "Staff"})` : "Sign In"}
              onClick={onOpenAuth}
              className="flex items-center justify-center rounded-xl p-1.5 text-slate-600 transition-colors hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-slate-800/80"
              title={isLoggedIn ? `Logged in as ${userEmail}` : "Sign In / Staff Portal"}
            >
              {isLoggedIn ? (
                <div className="relative flex h-6 w-6 items-center justify-center rounded-full bg-teal-600 text-[11px] font-bold text-white shadow-sm">
                  {(userEmail?.[0] || "U").toUpperCase()}
                  <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border border-white bg-emerald-500 dark:border-slate-900" />
                </div>
              ) : (
                <User className="h-4 w-4" />
              )}
            </button>
          </>
        )}
      </div>

      {/* Suggestions Combobox Dropdown */}
      {isOpen && (
        <div
          ref={listboxRef}
          id="place-search-suggestions-list"
          role="listbox"
          className="absolute left-0 right-0 top-full mt-2 max-h-80 overflow-y-auto rounded-2xl glass-panel-elevated p-2 shadow-glass-elevated animate-in fade-in-50 slide-in-from-top-2 border border-slate-200/70 dark:border-slate-800/80"
        >
          {/* Active Search Suggestions */}
          {query.trim().length >= 2 && mergedSuggestions.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center justify-between px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                <span>Places in India (GeoNames)</span>
                <span className="text-[9px] font-normal lowercase text-teal-600 dark:text-teal-400">
                  {mergedSuggestions.length} found
                </span>
              </div>

              {mergedSuggestions.map((place, idx) => {
                const isActive = activeIndex === idx;
                return (
                  <button
                    key={place.id}
                    id={`place-suggestion-${idx}`}
                    role="option"
                    aria-selected={isActive}
                    onClick={() => handleSelect(place)}
                    onMouseEnter={() => setActiveIndex(idx)}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                      isActive
                        ? "bg-teal-500/15 text-teal-900 dark:bg-teal-500/20 dark:text-teal-200 ring-1 ring-teal-500/30"
                        : "hover:bg-slate-200/50 dark:hover:bg-slate-800/50 text-slate-800 dark:text-slate-100"
                    }`}
                  >
                    <div
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${
                        place.isHub
                          ? "bg-teal-500/20 text-teal-600 dark:text-teal-300"
                          : "bg-slate-200/60 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                      }`}
                    >
                      {place.isHub ? <Building2 className="h-4 w-4" /> : <MapPin className="h-4 w-4" />}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="truncate font-medium text-slate-900 dark:text-white">
                          {renderHighlightedName(place.name, query)}
                        </div>
                        {place.isHub && (
                          <span className="shrink-0 rounded-full bg-teal-500/15 border border-teal-500/30 px-1.5 py-0.5 text-[9px] font-bold text-teal-700 dark:text-teal-300">
                            In top cities
                          </span>
                        )}
                      </div>
                      <div className="truncate text-xs text-slate-500 dark:text-slate-400">
                        {place.state} • {place.lat.toFixed(2)}°N, {place.lon.toFixed(2)}°E
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {/* No places found message */}
          {query.trim().length >= 2 && !isLoading && mergedSuggestions.length === 0 && (
            <div className="px-4 py-5 text-center text-xs font-medium text-slate-500 dark:text-slate-400">
              No places found in India for &ldquo;{query}&rdquo;
            </div>
          )}

          {/* Recent Searches (When input is empty or query < 2 chars) */}
          {query.trim().length < 2 && recentSearches.length > 0 && (
            <div className="space-y-1">
              <div className="flex items-center justify-between px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                <span>Recent Searches</span>
                <button
                  onClick={clearRecentSearches}
                  className="text-[10px] font-semibold text-slate-400 hover:text-rose-500 transition-colors lowercase"
                >
                  clear
                </button>
              </div>

              {recentSearches.map((place, idx) => {
                const isActive = activeIndex === idx;
                return (
                  <button
                    key={`recent-${idx}-${place.lat}-${place.lon}`}
                    id={`place-suggestion-${idx}`}
                    role="option"
                    aria-selected={isActive}
                    onClick={() => handleSelect(place)}
                    onMouseEnter={() => setActiveIndex(idx)}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                      isActive
                        ? "bg-slate-200/80 dark:bg-slate-800/80 text-slate-900 dark:text-white"
                        : "hover:bg-slate-200/50 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-200"
                    }`}
                  >
                    <Clock className="h-4 w-4 shrink-0 text-slate-400" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{place.name}</div>
                      {(place.state || place.admin1) && (
                        <div className="truncate text-xs text-slate-400">
                          {place.state || place.admin1}
                        </div>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {/* Quick Hubs Shortcuts when empty & no recent searches */}
          {query.trim().length < 2 && recentSearches.length === 0 && (
            <div className="p-3 text-center">
              <div className="mb-2 flex items-center justify-center gap-1 text-xs font-semibold text-teal-600 dark:text-teal-400">
                <Sparkles className="h-3.5 w-3.5" /> Top Indian Hubs
              </div>
              <div className="flex flex-wrap justify-center gap-1.5">
                {INDIAN_CITIES.slice(0, 6).map((hub) => (
                  <button
                    key={hub.name}
                    onClick={() => handleSelect(hub)}
                    className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-teal-500/10 hover:text-teal-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-teal-500/20 dark:hover:text-teal-300 transition-colors"
                  >
                    {hub.name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
