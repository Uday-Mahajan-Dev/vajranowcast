/**
 * VajraNowcast TypeScript Models
 * Strictly matching backend schemas in backend/app/models/schemas.py
 */

export const DEFAULT_DISCLAIMER = "Experimental AI nowcast product — not an official IMD weather warning.";

export type SeverityLevel = "none" | "weak" | "moderate" | "severe" | "very_severe";

export interface LocationInput {
  latitude: number;
  longitude: number;
}

export interface InputConditions {
  cape_index_derived?: number;
  cin_index_derived?: number;
  pw_index_derived?: number;
  temperature_2m?: number;
  relative_humidity?: number;
  cloud_cover?: number;
  wind_speed_10m?: number;
  wind_direction_10m?: number;
  precip_1hr_ago?: number;
  precip_last_3hr?: number;
  pressure_trend?: number;
  dew_point_depression?: number;
  surface_pressure?: number;
  [key: string]: any;
}

export interface ThunderstormPrediction {
  latitude: number;
  longitude: number;
  timestamp: string;
  prediction_time: string;
  input_time_ist?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  lead_time_hours: number;
  thunderstorm_probability: number;
  severity: SeverityLevel;
  lightning_probability: number;
  confidence: number;
  input_conditions?: InputConditions | null;
  contributing_factors?: Record<string, any> | null;
  extrapolated_lead_time: boolean;
  lead_time_note?: string | null;
  stale: boolean;
  cached_at?: string | null;
  stale_reason?: string | null;
  disclaimer: string;
}

export interface NowcastMetadata {
  model_version: string;
  model_type: string;
  data_sources: string[];
  optimal_threshold: number;
  decision_rule: string;
  target_description: string;
  thermodynamic_indices_description: string;
  features_count: number;
  target_lead_time: string;
  confidence_formula: string;
  snapped_coordinates: {
    latitude: number;
    longitude: number;
  };
  [key: string]: any;
}

export interface NowcastResponse {
  request_time: string;
  predictions: ThunderstormPrediction[];
  metadata: NowcastMetadata;
  stale: boolean;
  cached_at?: string | null;
  disclaimer: string;
}

export interface CitiesNowcastResponse {
  timestamp: string;
  cities_count: number;
  cities: Record<string, ThunderstormPrediction[]>;
  disclaimer: string;
}

export interface AlertResponse {
  alert_id: string;
  city: string;
  latitude: number;
  longitude: number;
  alert_type: string;
  severity: SeverityLevel;
  tier?: "watch" | "advisory" | "warning" | string;
  is_test?: boolean;
  thunderstorm_probability: number;
  lightning_probability: number;
  valid_from: string;
  valid_until: string;
  message: string;
  is_active: boolean;
  disclaimer: string;
}

export interface ActiveAlertsResponse {
  timestamp: string;
  count: number;
  alerts: AlertResponse[];
  disclaimer: string;
}

export interface GridPointPrediction {
  latitude: number;
  longitude: number;
  thunderstorm_probability: number;
  severity: SeverityLevel;
  lightning_probability: number;
  confidence: number;
  cape: number;
  cin: number;
  precipitable_water: number;
}

export interface GridResponse {
  generated_at: string;
  valid_until: string;
  lead_time_hours: number;
  total_points: number;
  resolution_deg: number;
  grid_resolution_km: number;
  stale: boolean;
  stale_reason?: string | null;
  points: GridPointPrediction[];
  disclaimer: string;
}

export interface LocalFieldCell {
  lat: number;
  lon: number;
  prob: number;
  precipitation: number;
}

export interface LocalFieldWind {
  speed_kmh: number;
  direction_deg: number;
}

export interface LocalField {
  grid_size: number;
  spacing_deg: number;
  center_lat: number;
  center_lon: number;
  lats: number[];
  lons: number[];
  wind_700hpa?: LocalFieldWind | null;
  cells: LocalFieldCell[];
}

export interface ReplayTimelineHour {
  hour_offset: number;
  time_ist: string;
  iso_time: string;
  probability: number;
  severity: SeverityLevel;
  temperature_2m?: number | null;
  relative_humidity?: number | null;
  cloud_cover?: number | null;
  precipitation: number;
  weather_code?: number | null;
  label_fired: boolean;
  outcome_next_hour?: boolean;
  classification?: "hit" | "miss" | "false_alarm" | "correct_negative" | string;
  is_onset?: boolean;
  is_replay_hour: boolean;
  local_field?: LocalField;
}

export interface HistoricalReplayEvent {
  event_id: string;
  event_name: string;
  city: string;
  state: string;
  latitude: number;
  longitude: number;
  date: string;
  hour_ist: string;
  hour_utc: string;
  synoptic_summary: string;
  source: string;
  source_url: string;
  computed_verdict?: "Hit" | "Miss" | "False Alarm" | "Correct Rejection" | string | null;
  headline_verdict?: string;
  verified_by_human: boolean;
  optimal_threshold?: number;
  is_onset_hit?: boolean;
  classification_counts?: {
    hits: number;
    misses: number;
    false_alarms: number;
    correct_negatives: number;
    onset_hits: number;
  };
  features_vector?: Record<string, number> | null;
  prediction?: {
    thunderstorm_probability: number;
    severity: SeverityLevel;
    lightning_probability: number;
    confidence: number;
    lead_time_hours: number;
    input_conditions?: InputConditions | null;
    contributing_factors?: Record<string, any> | null;
  } | null;
  actual_outcome?: {
    weather_code?: number | null;
    was_thunderstorm?: boolean | null;
    outcome_next_hour?: boolean;
  } | null;
  timeline?: ReplayTimelineHour[] | null;
}

export interface HistoricalResponse {
  request_time: string;
  date: string;
  hour: number;
  prediction: ThunderstormPrediction;
  actual_weather_code?: number | null;
  actual_was_thunderstorm?: boolean | null;
  disclaimer: string;
}

export interface DataSourceStatus {
  source_name: string;
  status: "active" | "degraded" | "planned" | string;
  last_updated: string;
  variables: string[];
}

export interface ModelInfo {
  model_name: string;
  model_type: string;
  lead_time: string;
  target_description: string;
  thermodynamic_indices_description: string;
  optimal_threshold: number;
  decision_rule: string;
  confidence_calibration: {
    description: string;
    base_confidence_formula: string;
    lead_time_factor_formula: string;
    final_confidence_formula: string;
    lead_factor_values: Record<string, number>;
  };
  lightning_model: {
    method: string;
    formula: string;
    description: string;
  };
  alert_tiers?: {
    watch: number;
    advisory: number;
    warning: number;
  };
  severity_bands: Record<string, string>;
  features: string[];
  num_features: number;
  roc_auc: number;
  disclaimer: string;
}

export interface GeocodingResult {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  elevation?: number;
  feature_code?: string;
  country_code: string;
  country: string;
  admin1?: string;
  admin2?: string;
  admin3?: string;
}
