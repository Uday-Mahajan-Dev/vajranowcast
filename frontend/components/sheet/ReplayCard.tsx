"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  HistoricalReplayEvent,
  ReplayTimelineHour,
  SeverityLevel,
} from "@/lib/types";
import { SEVERITY_CONFIG, getSeverityFromProbability } from "@/lib/constants";
import { formatProbability, formatISTTime } from "@/lib/utils";
import {
  Play,
  Pause,
  RotateCcw,
  ExternalLink,
  X,
  Sparkles,
  Info,
  Droplets,
  Thermometer,
  Cloud,
  Wind,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  HelpCircle,
} from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  CartesianGrid,
} from "recharts";

interface ReplayCardProps {
  replay: HistoricalReplayEvent;
  onExit: () => void;
  onHourSelect?: (hour: ReplayTimelineHour) => void;
}

const CLASSIFICATION_CONFIG: Record<
  string,
  { label: string; badgeClass: string; dotColor: string; bg: string; text: string }
> = {
  hit: {
    label: "Hit",
    badgeClass: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30",
    dotColor: "#10b981",
    bg: "bg-emerald-500/10 dark:bg-emerald-500/20 border-emerald-500/30",
    text: "text-emerald-800 dark:text-emerald-300",
  },
  miss: {
    label: "Miss",
    badgeClass: "bg-rose-500/20 text-rose-700 dark:text-rose-400 border border-rose-500/30",
    dotColor: "#f43f5e",
    bg: "bg-rose-500/10 dark:bg-rose-500/20 border-rose-500/30",
    text: "text-rose-800 dark:text-rose-300",
  },
  false_alarm: {
    label: "False Alarm",
    badgeClass: "bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-500/30",
    dotColor: "#f59e0b",
    bg: "bg-amber-500/10 dark:bg-amber-500/20 border-amber-500/30",
    text: "text-amber-800 dark:text-amber-300",
  },
  correct_negative: {
    label: "Correct Negative",
    badgeClass: "bg-slate-500/20 text-slate-700 dark:text-slate-300 border border-slate-500/30",
    dotColor: "#94a3b8",
    bg: "bg-slate-500/10 dark:bg-slate-500/20 border-slate-500/30",
    text: "text-slate-700 dark:text-slate-300",
  },
};

export const ReplayCard: React.FC<ReplayCardProps> = ({
  replay,
  onExit,
  onHourSelect,
}) => {
  const timeline = replay.timeline || [];
  const replayHourIndex = timeline.findIndex((t) => t.is_replay_hour);
  const initialIndex = replayHourIndex !== -1 ? replayHourIndex : 6;

  const [currentIndex, setCurrentIndex] = useState<number>(initialIndex);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const playTimerRef = useRef<NodeJS.Timeout | null>(null);

  const currentHourData: ReplayTimelineHour | undefined =
    timeline[currentIndex] || timeline[initialIndex];

  // Notify parent of hour change (to update pin marker color)
  useEffect(() => {
    if (currentHourData && onHourSelect) {
      onHourSelect(currentHourData);
    }
  }, [currentIndex, currentHourData, onHourSelect]);

  // Autoplay handler (1 second per step)
  useEffect(() => {
    if (isPlaying) {
      playTimerRef.current = setInterval(() => {
        setCurrentIndex((prev) => {
          if (prev >= timeline.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 1000);
    } else if (playTimerRef.current) {
      clearInterval(playTimerRef.current);
    }

    return () => {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    };
  }, [isPlaying, timeline.length]);

  const pReplay = replay.prediction?.thunderstorm_probability ?? (currentHourData?.probability || 0);
  const sevKey = (replay.prediction?.severity || currentHourData?.severity || "none") as SeverityLevel;
  const sevConfig = SEVERITY_CONFIG[sevKey] || SEVERITY_CONFIG.none;
  const isHit = replay.computed_verdict === "Hit";

  const counts = replay.classification_counts || {
    hits: timeline.filter((t) => t.classification === "hit").length,
    misses: timeline.filter((t) => t.classification === "miss").length,
    false_alarms: timeline.filter((t) => t.classification === "false_alarm").length,
    correct_negatives: timeline.filter((t) => t.classification === "correct_negative").length,
    onset_hits: timeline.filter((t) => t.is_onset).length,
  };

  // Chart data formatting
  const chartData = timeline.map((item, idx) => ({
    name: item.time_ist.replace(" IST", ""),
    prob: item.probability,
    rain: item.precipitation,
    isCurrent: idx === currentIndex,
    isReplay: item.is_replay_hour,
    item,
  }));

  const getVerdictExplanation = (verdict?: string | null, isOnset?: boolean, isReplayHour: boolean = true) => {
    if (verdict === "Hit") {
      if (isOnset) {
        return "Onset Hit: The model anticipated heavy rain before it began (P(TS) ≥ 0.186 while no rain was falling at this hour; heavy rain arrived at t+1).";
      }
      return "Reactive Alert: The model issued an alert (P(TS) ≥ 0.186), but rain was already falling at this hour (reacting to ongoing precipitation rather than anticipating onset).";
    }
    if (verdict === "Miss") {
      return "Miss: Heavy rain (> 2 mm) occurred in the next hour (t+1), but the model remained below the alert threshold (P(TS) < 0.186).";
    }
    if (verdict === "False Alarm") {
      return "False Alarm: The model crossed the alert threshold (P(TS) ≥ 0.186), but heavy rain did not follow in the next hour (t+1).";
    }
    return "Correct Negative: The model stayed below the alert threshold, and no heavy rain occurred in the next hour.";
  };

  return (
    <div className="space-y-4">
      {/* 1. Replay Mode Banner */}
      <div className="flex items-center justify-between rounded-2xl border border-violet-500/30 bg-violet-500/10 p-3 text-violet-900 dark:text-violet-200 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-xl bg-violet-600 text-white shadow-sm">
            <RotateCcw className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs font-bold">
              Historical Replay
            </div>
            <div className="text-[11px] text-violet-700 dark:text-violet-300 font-mono">
              {replay.date} • {replay.hour_ist}
            </div>
          </div>
        </div>
        <button
          onClick={onExit}
          className="flex items-center gap-1 rounded-xl bg-violet-600 px-3 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-violet-700 transition-colors"
        >
          <X className="h-3.5 w-3.5" />
          <span>Exit</span>
        </button>
      </div>

      {/* 2. Event Title & Metadata */}
      <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h2 className="text-base font-bold text-slate-900 dark:text-white leading-tight">
              {replay.event_name}
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {replay.city}, {replay.state} • ({replay.latitude.toFixed(2)}°N, {replay.longitude.toFixed(2)}°E)
            </p>
          </div>
          <div
            className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold uppercase tracking-wider ${
              isHit
                ? "bg-emerald-500/20 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30"
                : "bg-rose-500/20 text-rose-700 dark:text-rose-400 border border-rose-500/30"
            }`}
          >
            {isHit ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
            {replay.computed_verdict || "Hit"}
          </div>
        </div>

        <p className="mt-2.5 text-xs text-slate-600 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-800/50 p-2.5 rounded-xl border border-slate-200/50 dark:border-slate-700/50">
          {replay.synoptic_summary}
        </p>

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500 dark:text-slate-400">
          <div className="flex items-center gap-1.5">
            {!replay.verified_by_human && (
              <span className="inline-flex items-center rounded-md bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400 border border-amber-500/20">
                Reanalysis Target (t+1)
              </span>
            )}
            {replay.is_onset_hit && (
              <span className="inline-flex items-center rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                Onset Hit (Anticipated)
              </span>
            )}
          </div>
          {replay.source_url && (
            <a
              href={replay.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-teal-600 hover:underline dark:text-teal-400 font-medium"
            >
              <span>News Context</span>
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>

      {/* 3. 13-Hour Summary Banner */}
      <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-3.5 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
        <div className="text-[11px] font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-2 flex items-center justify-between">
          <span>13-Hour Window Summary</span>
          <span className="text-[10px] text-slate-500 font-normal">t−6h to t+6h</span>
        </div>

        <div className="grid grid-cols-4 gap-1.5 text-center">
          <div className="rounded-xl bg-emerald-500/10 p-2 border border-emerald-500/20 dark:bg-emerald-500/15">
            <div className="text-base font-black text-emerald-700 dark:text-emerald-400">
              {counts.hits}
            </div>
            <div className="text-[10px] font-semibold text-emerald-800 dark:text-emerald-300">
              {counts.hits === 1 ? "Hit" : "Hits"}
            </div>
          </div>
          <div className="rounded-xl bg-rose-500/10 p-2 border border-rose-500/20 dark:bg-rose-500/15">
            <div className="text-base font-black text-rose-700 dark:text-rose-400">
              {counts.misses}
            </div>
            <div className="text-[10px] font-semibold text-rose-800 dark:text-rose-300">
              {counts.misses === 1 ? "Miss" : "Misses"}
            </div>
          </div>
          <div className="rounded-xl bg-amber-500/10 p-2 border border-amber-500/20 dark:bg-amber-500/15">
            <div className="text-base font-black text-amber-700 dark:text-amber-400">
              {counts.false_alarms}
            </div>
            <div className="text-[10px] font-semibold text-amber-800 dark:text-amber-300">
              {counts.false_alarms === 1 ? "False Alarm" : "False Alarms"}
            </div>
          </div>
          <div className="rounded-xl bg-slate-500/10 p-2 border border-slate-500/20 dark:bg-slate-800/60">
            <div className="text-base font-black text-slate-700 dark:text-slate-300">
              {counts.correct_negatives}
            </div>
            <div className="text-[10px] font-semibold text-slate-600 dark:text-slate-400">
              Correct Neg.
            </div>
          </div>
        </div>

        <div className="mt-2 text-[11px] text-slate-600 dark:text-slate-300">
          Across these 13 hours:{" "}
          <span className="font-bold text-emerald-600 dark:text-emerald-400">{counts.hits} hit{counts.hits !== 1 ? "s" : ""}</span>,{" "}
          <span className="font-bold text-rose-600 dark:text-rose-400">{counts.misses} miss{counts.misses !== 1 ? "es" : ""}</span>,{" "}
          <span className="font-bold text-amber-600 dark:text-amber-400">{counts.false_alarms} false alarm{counts.false_alarms !== 1 ? "s" : ""}</span>
          {counts.onset_hits > 0 && (
            <span className="text-slate-500"> ({counts.onset_hits} onset anticipation)</span>
          )}.
        </div>
      </div>

      {/* 4. Model Verdict & Threshold Call */}
      <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
        <div className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider mb-2">
          Model Call at Replay Hour ({replay.hour_ist})
        </div>

        <div className="grid grid-cols-2 gap-3 mb-3">
          <div className="rounded-xl bg-slate-100/80 p-3 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
            <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
              Predicted Probability P(TS)
            </div>
            <div className="text-xl font-black text-slate-900 dark:text-white mt-0.5">
              {formatProbability(pReplay)}
            </div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">
              Threshold: <span className="font-bold text-teal-600 dark:text-teal-400">0.186 (18.6%)</span>
            </div>
          </div>

          <div className="rounded-xl bg-slate-100/80 p-3 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
            <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
              Predicted Severity
            </div>
            <div
              className={`inline-flex items-center rounded-lg px-2 py-0.5 text-xs font-bold mt-1 ${sevConfig.badgeClass}`}
            >
              {sevConfig.label}
            </div>
            <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">
              Confidence: {replay.prediction?.confidence ? `${Math.round(replay.prediction.confidence * 100)}%` : "--%"}
            </div>
          </div>
        </div>

        {/* Verdict Explanation */}
        <div
          className={`rounded-xl p-2.5 text-xs font-medium leading-relaxed ${
            isHit
              ? "bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 border border-emerald-500/20"
              : "bg-rose-500/10 text-rose-800 dark:text-rose-300 border border-rose-500/20"
          }`}
        >
          {getVerdictExplanation(replay.computed_verdict, replay.is_onset_hit, true)}
        </div>
      </div>

      {/* 5. Interactive Replay Timeline Player & Chart */}
      <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
        <div className="flex items-center justify-between mb-2">
          <div>
            <div className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider">
              Convective Timeline (t−6h to t+6h)
            </div>
            <div className="text-[11px] text-slate-500 dark:text-slate-400">
              Rainfall bars (mm) vs Model Probability P(TS) line
            </div>
          </div>

          {/* Player Controls */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className="flex h-8 w-8 items-center justify-center rounded-xl bg-teal-600 text-white shadow-sm hover:bg-teal-700 transition-all"
              title={isPlaying ? "Pause" : "Play Timeline"}
            >
              {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current ml-0.5" />}
            </button>
            <button
              onClick={() => {
                setIsPlaying(false);
                setCurrentIndex(initialIndex);
              }}
              className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 shadow-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
              title="Reset to Replay Hour"
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Recharts Timeline */}
        <div className="h-48 w-full mt-3 select-none">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={chartData}
              margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
              onClick={(e) => {
                if (e && e.activeTooltipIndex !== undefined) {
                  setIsPlaying(false);
                  setCurrentIndex(e.activeTooltipIndex);
                }
              }}
            >
              <CartesianGrid strokeDasharray="3 3" opacity={0.15} vertical={false} />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 9, fill: "#94a3b8" }}
                interval={1}
                tickLine={false}
              />
              <YAxis
                yAxisId="prob"
                domain={[0, 1]}
                tick={{ fontSize: 9, fill: "#94a3b8" }}
                tickFormatter={(v) => `${Math.round(v * 100)}%`}
                tickCount={4}
              />
              <YAxis
                yAxisId="rain"
                orientation="right"
                domain={[0, "auto"]}
                tick={{ fontSize: 9, fill: "#38bdf8" }}
                tickFormatter={(v) => `${v}mm`}
                hide={true}
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload || !payload.length) return null;
                  const d = payload[0].payload;
                  const item: ReplayTimelineHour = d.item;
                  const classConf = CLASSIFICATION_CONFIG[item.classification || ""] || CLASSIFICATION_CONFIG.correct_negative;

                  return (
                    <div className="rounded-xl border border-slate-200 bg-white/95 p-2.5 shadow-xl backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/95 text-xs">
                      <div className="font-bold text-slate-900 dark:text-white flex items-center justify-between gap-2">
                        <span>{item.time_ist}</span>
                        {item.is_replay_hour && (
                          <span className="rounded bg-teal-500/20 text-teal-600 dark:text-teal-400 px-1 py-0.5 text-[9px]">
                            Replay Hour
                          </span>
                        )}
                      </div>
                      <div className="mt-1.5 space-y-1 text-[11px]">
                        <div className="flex justify-between gap-3">
                          <span className="text-slate-500">P(TS):</span>
                          <span className="font-bold text-teal-600 dark:text-teal-400">
                            {formatProbability(item.probability)}
                          </span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span className="text-slate-500">Rainfall (t):</span>
                          <span className="font-bold text-sky-500">{item.precipitation} mm</span>
                        </div>
                        <div className="flex justify-between gap-3">
                          <span className="text-slate-500">Target (t+1):</span>
                          <span className={`font-semibold ${item.outcome_next_hour ? "text-rose-500" : "text-slate-500"}`}>
                            {item.outcome_next_hour ? "Heavy Rain (>2mm)" : "No Heavy Rain"}
                          </span>
                        </div>
                        <div className="flex justify-between gap-3 items-center pt-0.5 border-t border-slate-200 dark:border-slate-700">
                          <span className="text-slate-500">Classification:</span>
                          <span className={`rounded px-1.5 py-0.2 text-[10px] font-bold ${classConf.badgeClass}`}>
                            {item.is_onset ? "Onset Hit" : classConf.label}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                }}
              />
              {/* Optimal Threshold Line 0.186 */}
              <ReferenceLine
                yAxisId="prob"
                y={0.186}
                stroke="#0d9488"
                strokeDasharray="4 4"
                strokeWidth={1.5}
                label={{
                  value: "0.186 Threshold",
                  fill: "#0d9488",
                  fontSize: 9,
                  position: "top",
                }}
              />
              {/* Rain Bars */}
              <Bar
                yAxisId="rain"
                dataKey="rain"
                fill="#38bdf8"
                opacity={0.65}
                radius={[3, 3, 0, 0]}
              />
              {/* Probability Line with colored classification markers */}
              <Line
                yAxisId="prob"
                type="monotone"
                dataKey="prob"
                stroke="#0ea5e9"
                strokeWidth={2.5}
                dot={(props: any) => {
                  const isCurrent = props.index === currentIndex;
                  const item: ReplayTimelineHour = props.payload.item;
                  const classConf = CLASSIFICATION_CONFIG[item?.classification || ""] || CLASSIFICATION_CONFIG.correct_negative;

                  return (
                    <circle
                      key={`dot-${props.index}`}
                      cx={props.cx}
                      cy={props.cy}
                      r={isCurrent ? 6.5 : item?.is_replay_hour ? 5 : 3.5}
                      fill={isCurrent ? "#f43f5e" : classConf.dotColor}
                      stroke={item?.is_replay_hour ? "#0d9488" : "#fff"}
                      strokeWidth={isCurrent ? 2.5 : item?.is_replay_hour ? 2 : 1.5}
                    />
                  );
                }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {/* Timeline Classification Pill Strip */}
        <div className="mt-2.5 flex items-center justify-between gap-1 overflow-x-auto pb-1 scrollbar-none">
          {timeline.map((item, idx) => {
            const isSelected = idx === currentIndex;
            const classConf = CLASSIFICATION_CONFIG[item.classification || ""] || CLASSIFICATION_CONFIG.correct_negative;
            return (
              <button
                key={`pill-${idx}`}
                onClick={() => {
                  setIsPlaying(false);
                  setCurrentIndex(idx);
                }}
                className={`flex flex-col items-center flex-1 min-w-[28px] py-1 px-0.5 rounded-lg text-[9px] font-medium transition-all ${
                  isSelected
                    ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900 ring-2 ring-teal-500 scale-105"
                    : "bg-slate-100/70 dark:bg-slate-800/50 hover:bg-slate-200 dark:hover:bg-slate-700/60"
                }`}
                title={`${item.time_ist}: ${classConf.label}`}
              >
                <span className="font-mono text-[8px] opacity-75">
                  {item.time_ist.split(":")[0]}
                </span>
                <span
                  className="mt-0.5 h-2 w-2 rounded-full"
                  style={{ backgroundColor: classConf.dotColor }}
                />
              </button>
            );
          })}
        </div>

        {/* Scrubber Range Input */}
        <div className="mt-2">
          <div className="flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400 mb-1">
            <span>Scrub Timeline</span>
            <span className="font-bold text-slate-900 dark:text-white">
              {currentHourData?.time_ist} ({currentHourData?.hour_offset === 0 ? "Replay Hour" : `${(currentHourData?.hour_offset ?? 0) > 0 ? "+" : ""}${currentHourData?.hour_offset}h`})
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={timeline.length - 1}
            value={currentIndex}
            onChange={(e) => {
              setIsPlaying(false);
              setCurrentIndex(Number(e.target.value));
            }}
            className="w-full accent-teal-600 cursor-pointer"
          />
        </div>
      </div>

      {/* 6. Selected Hour Classification & Atmospheric Conditions Strip */}
      {currentHourData && (
        <div className="rounded-2xl border border-slate-200/80 bg-white/80 p-4 shadow-sm dark:border-slate-800/80 dark:bg-slate-900/70">
          <div className="text-xs font-bold text-slate-900 dark:text-white uppercase tracking-wider mb-2 flex items-center justify-between">
            <span>Evaluation at {currentHourData.time_ist}</span>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                CLASSIFICATION_CONFIG[currentHourData.classification || ""]?.badgeClass || "bg-slate-500/20 text-slate-300"
              }`}
            >
              {currentHourData.is_onset
                ? "Onset Hit"
                : CLASSIFICATION_CONFIG[currentHourData.classification || ""]?.label || "Correct Negative"}
            </span>
          </div>

          <p className="text-xs text-slate-600 dark:text-slate-300 mb-3 bg-slate-50 dark:bg-slate-800/40 p-2.5 rounded-xl border border-slate-200/50 dark:border-slate-700/40">
            {getVerdictExplanation(
              currentHourData.classification === "hit" ? "Hit" : currentHourData.classification === "miss" ? "Miss" : currentHourData.classification === "false_alarm" ? "False Alarm" : "Correct Negative",
              currentHourData.is_onset,
              currentHourData.is_replay_hour
            )}
          </p>

          <div className="grid grid-cols-4 gap-2 text-center text-xs">
            <div className="rounded-xl bg-slate-100/80 p-2 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
              <Thermometer className="mx-auto h-3.5 w-3.5 text-amber-500 mb-1" />
              <div className="text-[10px] text-slate-400">Temp</div>
              <div className="font-bold text-slate-900 dark:text-white">
                {currentHourData.temperature_2m ?? "--"}°C
              </div>
            </div>

            <div className="rounded-xl bg-slate-100/80 p-2 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
              <Droplets className="mx-auto h-3.5 w-3.5 text-sky-500 mb-1" />
              <div className="text-[10px] text-slate-400">Humidity</div>
              <div className="font-bold text-slate-900 dark:text-white">
                {currentHourData.relative_humidity ?? "--"}%
              </div>
            </div>

            <div className="rounded-xl bg-slate-100/80 p-2 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
              <Cloud className="mx-auto h-3.5 w-3.5 text-slate-400 mb-1" />
              <div className="text-[10px] text-slate-400">Cloud</div>
              <div className="font-bold text-slate-900 dark:text-white">
                {currentHourData.cloud_cover ?? "--"}%
              </div>
            </div>

            <div className="rounded-xl bg-slate-100/80 p-2 dark:bg-slate-800/60 border border-slate-200/50 dark:border-slate-700/50">
              <Droplets className="mx-auto h-3.5 w-3.5 text-teal-500 mb-1" />
              <div className="text-[10px] text-slate-400">Rain (t)</div>
              <div className="font-bold text-slate-900 dark:text-white">
                {currentHourData.precipitation} mm
              </div>
            </div>
          </div>

          {/* Storm Impact Zone & Mid-Level Wind Status */}
          {currentHourData.local_field && (
            <div className="mt-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 p-3 border border-slate-200/60 dark:border-slate-700/60 text-xs">
              <div className="flex items-center justify-between mb-1.5 font-semibold text-slate-800 dark:text-slate-200">
                <span className="flex items-center gap-1.5">
                  <Wind className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400" />
                  Storm Impact Zone & Steering Wind
                </span>
                <span className="text-[10px] font-normal text-slate-400">5×5 Grid (≈ 110 km × 110 km)</span>
              </div>

              <div className="text-[11px] text-slate-600 dark:text-slate-300 space-y-1">
                {currentHourData.local_field.wind_700hpa ? (
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">700 hPa Steering Wind:</span>
                    <span className="font-bold text-teal-600 dark:text-teal-400">
                      {currentHourData.local_field.wind_700hpa.speed_kmh} km/h @ {currentHourData.local_field.wind_700hpa.direction_deg}°
                    </span>
                  </div>
                ) : (
                  <div className="text-slate-400 italic">
                    Track unavailable (no mid-level wind data)
                  </div>
                )}
                <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-200/60 dark:border-slate-700/40">
                  Model risk area + archive rainfall. Not radar.
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 7. Archive Note */}
      <div className="rounded-xl bg-slate-100/70 p-2.5 text-[11px] text-slate-500 dark:bg-slate-900/50 dark:text-slate-400 border border-slate-200/50 dark:border-slate-800/50">
        <div className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-300">
          <Info className="h-3.5 w-3.5 text-teal-600 dark:text-teal-400" />
          Archive Dataset Note
        </div>
        <p className="mt-0.5 leading-relaxed">
          Rainfall shown is archive reanalysis data (ERA5-Land / Open-Meteo Historical Archive), not station observations. The evaluation target is heavy rain (&gt; 2.0 mm) occurring in the subsequent hour (t+1).
        </p>
      </div>
    </div>
  );
};
