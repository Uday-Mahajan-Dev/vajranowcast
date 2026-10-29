"use client";

import { useState, useEffect } from "react";
import { fetchModelInfoCached } from "./api";
import { OPTIMAL_THRESHOLD } from "./constants";
import { ModelInfo } from "./types";

export interface UseModelInfoResult {
  modelInfo: ModelInfo | null;
  optimalThreshold: number;
  modelVersion: string;
  thresholdPercent: string;
  isLoading: boolean;
}

export function useModelInfo(): UseModelInfoResult {
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    fetchModelInfoCached()
      .then((info) => {
        if (mounted) {
          setModelInfo(info);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        // Fall back gracefully to v1 defaults
        console.warn("Model info fetch failed, falling back to v1 defaults:", err);
        if (mounted) {
          setIsLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  const optimalThreshold =
    typeof modelInfo?.optimal_threshold === "number"
      ? modelInfo.optimal_threshold
      : OPTIMAL_THRESHOLD;

  const rawVersion = modelInfo?.model_version || "v1";
  const modelVersion = rawVersion.toLowerCase().startsWith("v")
    ? rawVersion
    : `v${rawVersion}`;

  const thresholdPercent = (optimalThreshold * 100).toFixed(1);

  return {
    modelInfo,
    optimalThreshold,
    modelVersion,
    thresholdPercent,
    isLoading,
  };
}
