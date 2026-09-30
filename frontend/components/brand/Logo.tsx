import React from "react";

interface LogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  showText?: boolean;
}

export const Logo: React.FC<LogoProps> = ({
  className = "",
  size = "md",
  showText = true,
}) => {
  const iconSizes = {
    sm: "w-6 h-6",
    md: "w-7 h-7",
    lg: "w-9 h-9",
  };

  const textSizes = {
    sm: "text-sm",
    md: "text-base",
    lg: "text-xl",
  };

  return (
    <div className={`flex items-center gap-2 select-none ${className}`}>
      {/* Custom Vajra stylized hexagonal storm shield + thunderbolt */}
      <div
        className={`relative flex items-center justify-center rounded-xl bg-gradient-to-br from-teal-500 via-cyan-600 to-indigo-700 p-1.5 shadow-md shadow-teal-900/20 text-white ${iconSizes[size]}`}
      >
        <svg
          viewBox="0 0 24 24"
          fill="currentColor"
          className="w-full h-full drop-shadow-sm"
        >
          {/* Dual vajra lightning prism */}
          <path d="M13 2L4.5 13.5H11L9.5 22L19.5 10.5H13L14.5 2Z" fill="#facc15" />
          <path
            d="M11 2L5.5 11.5H10.5L9.5 18L17.5 9.5H12L13 2Z"
            fill="#ffffff"
            opacity="0.85"
          />
        </svg>
      </div>

      {showText && (
        <div className="flex flex-col leading-tight">
          <div className="flex items-center gap-1">
            <span
              className={`font-black tracking-tight text-slate-900 dark:text-white ${textSizes[size]}`}
            >
              Vajra<span className="text-teal-600 dark:text-teal-400">Nowcast</span>
            </span>
            <span className="rounded bg-teal-500/10 px-1 py-0.2 text-[9px] font-bold text-teal-600 dark:text-teal-400 border border-teal-500/20">
              v1.1
            </span>
          </div>
          <span className="text-[10px] font-medium tracking-wide text-slate-500 dark:text-slate-400">
            India Convective AI
          </span>
        </div>
      )}
    </div>
  );
};
