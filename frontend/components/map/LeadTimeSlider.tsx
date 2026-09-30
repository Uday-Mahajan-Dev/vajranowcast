"use client";

import React from "react";

export type LeadTimeOption = 0 | 1 | 2 | 3 | 6;

interface LeadTimeSliderProps {
  currentLead: LeadTimeOption;
  onChangeLead: (lead: LeadTimeOption) => void;
  isGridLeadFixed?: boolean;
  baseTime?: Date | string | null;
  className?: string;
}

export const LeadTimeSlider: React.FC<LeadTimeSliderProps> = ({
  currentLead,
  onChangeLead,
  isGridLeadFixed = true,
  baseTime,
  className = "",
}) => {
  const leads: { value: LeadTimeOption; label: string }[] = [
    { value: 0, label: "Now" },
    { value: 1, label: "+1h" },
    { value: 2, label: "+2h" },
    { value: 3, label: "+3h" },
    { value: 6, label: "+6h" },
  ];

  // Compute IST start and end window
  const now = baseTime ? (typeof baseTime === "string" ? new Date(baseTime) : baseTime) : new Date();
  const curUtc = now.getTime() + (now.getTimezoneOffset() * 60000);
  const istDate = new Date(curUtc + (330 * 60000)); // +5:30
  const curHour = istDate.getHours();
  const startHour = (curHour + currentLead) % 24;
  const endHour = (startHour + 1) % 24;
  const timeWindowLabel = `Showing ${String(startHour).padStart(2, "0")}:00–${String(endHour).padStart(2, "0")}:00 IST`;

  return (
    <div
      className={`fixed top-20 left-1/2 -translate-x-1/2 z-20 select-none ${className}`}
    >
      <div className="flex flex-col items-center gap-1 rounded-2xl glass-panel-elevated px-3 py-1.5 shadow-glass">
        {/* Chips */}
        <div className="flex items-center gap-1">
          {leads.map((lead) => {
            const isSelected = currentLead === lead.value;
            return (
              <button
                key={lead.value}
                onClick={() => onChangeLead(lead.value)}
                className={`rounded-xl px-3 py-1 text-xs font-bold transition-all ${
                  isSelected
                    ? "bg-teal-600 text-white shadow-md shadow-teal-900/20 dark:bg-teal-500"
                    : "text-slate-600 hover:bg-slate-200/50 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800/60 dark:hover:text-white"
                }`}
              >
                {lead.label}
              </button>
            );
          })}
        </div>

        {/* Visible Time Window Label & Grid Note */}
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 dark:text-slate-300">
          <span>{timeWindowLabel}</span>
          {isGridLeadFixed && currentLead !== 0 && (
            <span className="text-[10px] text-amber-500 font-medium">
              • Grid shows Now only
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
