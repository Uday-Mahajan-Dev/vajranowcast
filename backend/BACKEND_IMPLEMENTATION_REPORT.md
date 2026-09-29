# VajraNowcast — Backend Implementation & API Specification Report

**System Name:** VajraNowcast Backend Engine  
**Version:** `1.0.0`  
**Problem Statement ID:** 26072 (Ministry of Earth Sciences / India Meteorological Department)  
**Target Domain:** AI-Powered Thunderstorm & Lightning Nowcasting (0–6 Hour Lead Time) for India  
**Date Generated:** September 29, 2026  

---

## 1. Executive Summary

The **VajraNowcast** backend is a high-performance, asynchronous REST API service built on **FastAPI** and **Python 3.12**. It ingests real-time atmospheric data from the Open-Meteo API, constructs a 24-dimensional meteorological state vector, and executes a pre-trained, calibrated machine learning model (`HistGradientBoostingClassifier` wrapped in `CalibratedClassifierCV` with isotonic regression) to deliver probabilistic thunderstorm and lightning predictions across the Indian subcontinent ($6.0^\circ\text{ N} - 38.0^\circ\text{ N}$, $68.0^\circ\text{ E} - 98.0^\circ\text{ E}$).

### Key Performance & Operational Constants
- **Lead Time:** $t+1$ hour forward nowcasting (extended to $0, 1, 2, 3, 6$ hours).
- **Model ROC-AUC:** $0.9467$ on unseen test data across 10 Indian metropolitan test sites ($2022–2024$).
- **Natural Class Prevalence:** $1.5\%$ positive convective events.
- **Optimal Decision Threshold:** `0.1860` (calibrated via F1-maximization on precision-recall curves to avoid imbalanced default $0.50$ failure).
- **Alert Trigger Threshold:** $\ge 0.60$ ($60\%$ probability).
- **Severe Storm Threshold:** $\ge 0.75$ ($75\%$ probability).
- **Inference Latency:** $<5\text{ ms}$ on CPU.
- **Data Ingestion Buffer:** $1\text{ past day}$ (`past_days=1`) for persistence & trend calculations.

---

## 2. File & Component Architecture

The backend repository layout is structured modularly under `backend/app/`:

```
backend/
├── .env                              # Environment configuration (Supabase, URLs, bounds)
├── Dockerfile                        # Containerization setup
├── requirements.txt                  # Python dependencies
└── app/
    ├── __init__.py
    ├── config.py                     # Pydantic Settings configuration loader
    ├── main.py                       # FastAPI application entry point, lifespan, & CORS
    ├── api/
    │   ├── __init__.py
    │   └── routes/
    │       ├── __init__.py
    │       ├── alerts.py             # Active alerts and batch alert generation routes
    │       ├── predictions.py        # Location nowcasts, city batch, & historical replay
    │       └── weather.py            # Live weather, instability indices, & source status
    ├── ml/
    │   ├── __init__.py
    │   ├── models/
    │   │   ├── __init__.py
    │   │   └── thunderstorm_model.py # ML model loader, rule-based fallback, severity & lightning predictors
    │   └── saved_models/
    │       ├── feature_columns.pkl   # List of 24 feature names in exact order
    │       ├── model_metadata.json   # Model training metadata & ROC-AUC score
    │       ├── optimal_threshold.pkl # Serialized float threshold (0.1860)
    │       ├── thunderstorm_model.pkl# Trained CalibratedClassifierCV estimator
    │       └── thunderstorm_scaler.pkl# Trained StandardScaler instance
    ├── models/
    │   ├── __init__.py
    │   ├── database.py               # Supabase client helper functions (anon & admin)
    │   └── schemas.py                # Pydantic v2 schemas and validation models
    └── services/
        ├── __init__.py
        ├── alert_service.py          # Alert evaluation, Supabase persistence, & expiry
        ├── data_ingestion.py         # Open-Meteo HTTP ingestion & city multi-fetch
        ├── feature_engineering.py    # 24-feature vector computation & persistence metrics
        └── ml_inference.py           # End-to-end NowcastingService orchestrator
```

---

## 3. The 24-Feature Vector & Engineering Pipeline

The model strictly consumes **24 features** in this precise index order:

| Index | Feature Key | Source | Physical Description |
|---|---|---|---|
| 0 | `cape` | Open-Meteo | Convective Available Potential Energy ($\text{J/kg}$) |
| 1 | `cin` | Open-Meteo | Convective Inhibition ($\text{J/kg}$) (absolute value) |
| 2 | `temperature_2m` | Open-Meteo | $2\text{m}$ Surface Air Temperature ($^\circ\text{C}$) |
| 3 | `dewpoint_2m` | Open-Meteo | $2\text{m}$ Dew Point Temperature ($^\circ\text{C}$) |
| 4 | `relative_humidity` | Open-Meteo | Surface Relative Humidity ($\%$) |
| 5 | `surface_pressure` | Open-Meteo | Surface Atmospheric Pressure ($\text{hPa}$) |
| 6 | `wind_speed_10m` | Open-Meteo | $10\text{m}$ Wind Speed ($\text{m/s}$) |
| 7 | `wind_direction_10m` | Open-Meteo | $10\text{m}$ Wind Direction ($^\circ$) |
| 8 | `cloud_cover` | Open-Meteo | Total Cloud Cover ($\%$) |
| 9 | `precipitable_water` | Open-Meteo | Total Column Integrated Water Vapour ($\text{mm}$ or $\text{kg/m}^2$) |
| 10 | `dew_point_depression` | Computed | $T_{2\text{m}} - T_{d,2\text{m}}$ ($\ge 0^\circ\text{C}$) |
| 11 | `cape_cin_ratio` | Computed | $\text{CAPE} / \max(\|\text{CIN}\|, 1)$ |
| 12 | `hour_sin` | Computed | $\sin(2\pi \cdot \text{hour} / 24)$ (diurnal cycle) |
| 13 | `hour_cos` | Computed | $\cos(2\pi \cdot \text{hour} / 24)$ (diurnal cycle) |
| 14 | `month_sin` | Computed | $\sin(2\pi \cdot \text{month} / 12)$ (seasonal cycle) |
| 15 | `month_cos` | Computed | $\cos(2\pi \cdot \text{month} / 12)$ (seasonal cycle) |
| 16 | `latitude` | User / Location | Latitude coordinate in decimal degrees |
| 17 | `longitude` | User / Location | Longitude coordinate in decimal degrees |
| 18 | `precip_1hr_ago` | Open-Meteo (past) | Hourly precipitation $1\text{ hour}$ prior ($\text{mm}$) |
| 19 | `precip_last_3hr` | Open-Meteo (past) | Cumulative precipitation over last $3\text{ hours}$ ($\text{mm}$) |
| 20 | `storm_2hr_ago` | Open-Meteo (past) | Convective weather code indicator $2\text{ hours}$ prior ($1.0$ or $0.0$) |
| 21 | `cloud_trend` | Open-Meteo (past) | Cloud cover delta: $\text{cloud}_{\text{now}} - \text{cloud}_{-1\text{h}}$ ($\%$) |
| 22 | `temp_trend` | Open-Meteo (past) | Temperature delta: $T_{\text{now}} - T_{-1\text{h}}$ ($^\circ\text{C}$) |
| 23 | `pressure_trend` | Open-Meteo (past) | Pressure delta: $P_{\text{now}} - P_{-1\text{h}}$ ($\text{hPa}$) |

> **Data Leakage Safeguard:** Concurrent precipitation (`precipitation` at time $t$) and immediate storm activity (`storm_1hr_ago`) are **strictly excluded**. Since the goal is $t+1$ prospective nowcasting, only antecedent and state features are permitted.

---

## 4. Complete API Endpoint Catalog & Technical Specifications

Below is the exhaustive documentation of all 10 API endpoints exposed by the service.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             VAJRANOWCAST API ROUTES                              │
├────────┬──────────────────────────────────────────┬──────────────────────────────┤
│ Method │ Path                                     │ Purpose                      │
├────────┼──────────────────────────────────────────┼──────────────────────────────┤
│ GET    │ /health                                  │ Health & Model Readiness     │
│ GET    │ /                                        │ API Discovery & Endpoints    │
│ GET    │ /api/v1/predictions/nowcast              │ Hyperlocal Location Nowcast  │
│ GET    │ /api/v1/predictions/nowcast/cities       │ Batch Metros Nowcast (10)    │
│ GET    │ /api/v1/predictions/historical           │ Hindcast Replay & Validation │
│ GET    │ /api/v1/weather/current                  │ Raw Real-time Weather        │
│ GET    │ /api/v1/weather/indices                  │ Instability Indices (CAPE..) │
│ GET    │ /api/v1/weather/sources/status           │ Meteorological Feeds Health  │
│ GET    │ /api/v1/alerts/active                    │ Live Weather Alerts          │
│ POST   │ /api/v1/alerts/generate                  │ Trigger Metros Alert Scan    │
└────────┴──────────────────────────────────────────┴──────────────────────────────┘
```

---

### 4.1 System & Discovery Endpoints

#### 1. `GET /health`
- **Description:** Verifies service health, returns model loading status and current optimal decision threshold.
- **Inputs:** None.
- **Downstream Calls:** Calls `ThunderstormClassifier.is_trained`.
- **Response Status:** `200 OK`
- **Response Payload:**
```json
{
  "status": "healthy",
  "service": "vajranowcast",
  "model_loaded": true,
  "optimal_threshold": 0.186
}
```

---

#### 2. `GET /`
- **Description:** Root metadata discovery endpoint listing available primary route paths and documentation URL.
- **Inputs:** None.
- **Downstream Calls:** None.
- **Response Status:** `200 OK`
- **Response Payload:**
```json
{
  "message": "VajraNowcast API",
  "docs": "/docs",
  "endpoints": [
    "/api/v1/predictions/nowcast",
    "/api/v1/weather/current",
    "/api/v1/alerts/active"
  ]
}
```

---

### 4.2 Predictions & Nowcasting Endpoints

#### 3. `GET /api/v1/predictions/nowcast`
- **Description:** Performs hyperlocal forward nowcasting for any latitude/longitude within India for specified lead times (default $0, 1, 2, 3, 6$ hours).
- **Inputs (Query Parameters):**
  - `lat` (*float*, required): Latitude between $6.0$ and $38.0$.
  - `lon` (*float*, required): Longitude between $68.0$ and $98.0$.
  - `lead_hours` (*string*, optional, default: `"0,1,2,3,6"`): Comma-separated list of lead time offsets in hours.
- **Downstream Calls:**
  1. `OpenMeteoService.fetch_current_weather(lat, lon)` (Open-Meteo Forecast API with `past_days=1`).
  2. `FeatureEngineer.build_feature_vector()` (constructs the 24-feature vector).
  3. `ThunderstormClassifier.predict()` (`StandardScaler` transform + `HistGradientBoosting` probability).
  4. `LightningPredictor.predict()` (derives lightning probability & confidence).
  5. `SeverityClassifier.classify()` (computes severity category).
- **Response Status:** `200 OK`
- **Response Payload Example:**
```json
{
  "request_time": "2026-09-29T10:30:00.000000Z",
  "predictions": [
    {
      "latitude": 28.61,
      "longitude": 77.21,
      "timestamp": "2026-09-29T10:30:00.000000Z",
      "prediction_time": "2026-09-29T10:30:00.000000Z",
      "lead_time_hours": 0.0,
      "thunderstorm_probability": 0.0412,
      "severity": "none",
      "lightning_probability": 0.0288,
      "confidence": 0.85,
      "contributing_factors": {
        "cape": 340.0,
        "cin": 131.0,
        "relative_humidity": 89.0,
        "dew_point_depression": 2.0,
        "precipitable_water": 33.3,
        "precip_last_3hr": 0.2,
        "pressure_trend": 0.5
      }
    },
    {
      "latitude": 28.61,
      "longitude": 77.21,
      "timestamp": "2026-09-29T10:30:00.000000Z",
      "prediction_time": "2026-09-29T11:30:00.000000Z",
      "lead_time_hours": 1.0,
      "thunderstorm_probability": 0.0391,
      "severity": "none",
      "lightning_probability": 0.0274,
      "confidence": 0.782,
      "contributing_factors": {
        "cape": 340.0,
        "cin": 131.0,
        "relative_humidity": 89.0,
        "dew_point_depression": 2.0,
        "precipitable_water": 33.3,
        "precip_last_3hr": 0.2,
        "pressure_trend": 0.5
      }
    }
  ],
  "metadata": {
    "model_version": "1.0.0-calibrated-hgbc",
    "model_type": "HistGradientBoostingClassifier + CalibratedClassifierCV",
    "data_sources": [
      "Open-Meteo Forecast API",
      "GFS-0.25"
    ],
    "optimal_threshold": 0.186,
    "decision_rule": "P(TS) >= 0.186 signifies high storm threat",
    "features_count": 24,
    "target_lead_time": "t+1 hour"
  }
}
```

---

#### 4. `GET /api/v1/predictions/nowcast/cities`
- **Description:** Concurrently triggers real-time nowcasts across 10 major Indian hubs: Delhi, Mumbai, Kolkata, Chennai, Bengaluru, Hyderabad, Jaipur, Lucknow, Guwahati, and Pune.
- **Inputs:** None.
- **Downstream Calls:**
  - `NowcastingService.predict_for_cities()` using `asyncio.gather` on all 10 cities concurrently.
- **Response Status:** `200 OK`
- **Response Payload Structure:**
```json
{
  "timestamp": "2026-09-29T10:30:00.000000Z",
  "cities_count": 10,
  "cities": {
    "Delhi": [ { "lead_time_hours": 0.0, "thunderstorm_probability": 0.04, ... }, ... ],
    "Mumbai": [ ... ],
    "Kolkata": [ ... ],
    "Chennai": [ ... ],
    "Bengaluru": [ ... ],
    "Hyderabad": [ ... ],
    "Jaipur": [ ... ],
    "Lucknow": [ ... ],
    "Guwahati": [ ... ],
    "Pune": [ ... ]
  }
}
```

---

#### 5. `GET /api/v1/predictions/historical`
- **Description:** Historical hindcast replay and verification endpoint. Queries Open-Meteo Historical Archive, extracts historical conditions for a chosen date and hour, runs inference, and verifies against actual recorded WMO convective weather codes.
- **Inputs (Query Parameters):**
  - `lat` (*float*, required): Latitude ($6.0$ to $38.0$).
  - `lon` (*float*, required): Longitude ($68.0$ to $98.0$).
  - `date` (*string*, required): Target date in `YYYY-MM-DD` format (e.g., `2024-05-15`).
  - `hour` (*int*, required): UTC/local hour between $0$ and $23$.
- **Downstream Calls:**
  1. `OpenMeteoService.fetch_historical_weather(lat, lon, date)` (`https://archive-api.open-meteo.com/v1/archive`).
  2. `FeatureEngineer.build_feature_vector_simple()` for index `hour`.
  3. `ThunderstormClassifier.predict()`.
  4. Compares observed `weather_code` against convective set $\{80, 81, 82, 85, 91, 92, 93, 95, 96, 99\}$.
- **Response Status:** `200 OK`
- **Response Payload Example:**
```json
{
  "request_time": "2026-09-29T10:30:00.000000Z",
  "date": "2024-05-15",
  "hour": 15,
  "prediction": {
    "latitude": 28.61,
    "longitude": 77.21,
    "timestamp": "2026-09-29T10:30:00.000000Z",
    "prediction_time": "2024-05-15T15:00:00",
    "lead_time_hours": 1.0,
    "thunderstorm_probability": 0.0001,
    "severity": "none",
    "lightning_probability": 0.0001,
    "confidence": 0.85,
    "contributing_factors": {
      "cape": 0.0,
      "cin": 0.0,
      "relative_humidity": 8.0,
      "dew_point_depression": 40.9,
      "precipitable_water": 30.0,
      "precip_last_3hr": 0.0,
      "pressure_trend": 0.0
    }
  },
  "actual_weather_code": 0,
  "actual_was_thunderstorm": false
}
```

---

### 4.3 Meteorological Data & Index Endpoints

#### 6. `GET /api/v1/weather/current`
- **Description:** Returns live atmospheric observations and hourly forecast arrays directly from Open-Meteo for a given location.
- **Inputs (Query Parameters):**
  - `lat` (*float*, optional, default: `28.61`): Latitude.
  - `lon` (*float*, optional, default: `77.21`): Longitude.
- **Downstream Calls:**
  - `OpenMeteoService.fetch_current_weather(lat, lon)`.
- **Response Status:** `200 OK`
- **Response Payload Example:**
```json
{
  "latitude": 28.61,
  "longitude": 77.21,
  "request_time": "2026-09-29T10:30:00.000000+00:00",
  "weather": {
    "latitude": 28.625,
    "longitude": 77.25,
    "current": {
      "temperature_2m": 26.4,
      "relative_humidity_2m": 82,
      "surface_pressure": 986.2,
      "precipitation": 0.0,
      "weather_code": 2
    },
    "hourly": { ... }
  }
}
```

---

#### 7. `GET /api/v1/weather/indices`
- **Description:** Computes specialized thermodynamic instability indices including CAPE category, CIN, CAPE/CIN ratio, Dew Point Depression, Precipitable Water, and Convective Potential assessment.
- **Inputs (Query Parameters):**
  - `lat` (*float*, optional, default: `28.61`): Latitude.
  - `lon` (*float*, optional, default: `77.21`): Longitude.
- **Downstream Calls:**
  - `OpenMeteoService.fetch_current_weather(lat, lon)`.
  - `FeatureEngineer.build_feature_vector()`.
- **Response Status:** `200 OK`
- **Response Payload Example:**
```json
{
  "latitude": 28.61,
  "longitude": 77.21,
  "timestamp": "2026-09-29T10:30:00.000000+00:00",
  "indices": {
    "cape_j_kg": 340.0,
    "cape_category": "None",
    "cin_j_kg": 131.0,
    "cape_cin_ratio": 2.6,
    "dew_point_depression_c": 2.0,
    "precipitable_water_mm": 33.3,
    "relative_humidity_pct": 89.0,
    "surface_pressure_hpa": 985.9,
    "convective_potential": "Stable / Nil Severe Activity"
  }
}
```

---

#### 8. `GET /api/v1/weather/sources/status`
- **Description:** Health and operational readiness probe across the 4 primary meteorological data feeds (Open-Meteo, NOAA GFS, ISRO MOSDAC, Blitzortung). Performs live probe of Open-Meteo.
- **Inputs:** None.
- **Downstream Calls:**
  - Live probe test call to Open-Meteo Forecast endpoint.
- **Response Status:** `200 OK`
- **Response Payload Example:**
```json
[
  {
    "source_name": "Open-Meteo High-Resolution NWP",
    "status": "active",
    "last_updated": "2026-09-29T10:30:00.000000+00:00",
    "variables": [
      "temperature_2m",
      "dew_point_2m",
      "relative_humidity_2m",
      "surface_pressure",
      "wind_speed_10m",
      "wind_direction_10m",
      "cloud_cover",
      "precipitation",
      "cape",
      "convective_inhibition",
      "precipitable_water"
    ]
  },
  {
    "source_name": "NOAA GFS 0.25° Global Forecast",
    "status": "configured",
    "last_updated": "2026-09-29T10:30:00.000000+00:00",
    "variables": [
      "HGT_clb",
      "CAPE_sfc",
      "CIN_sfc",
      "PWAT_ea",
      "UGRD_10m",
      "VGRD_10m"
    ]
  },
  {
    "source_name": "ISRO MOSDAC INSAT-3D/3DR",
    "status": "configured",
    "last_updated": "2026-09-29T10:30:00.000000+00:00",
    "variables": [
      "Cloud Top Brightness Temp (TIR1)",
      "Water Vapor (WV)",
      "Rainfall Rate (HEM)"
    ]
  },
  {
    "source_name": "Blitzortung TOA Lightning Network",
    "status": "configured",
    "last_updated": "2026-09-29T10:30:00.000000+00:00",
    "variables": [
      "stroke_timestamp",
      "stroke_lat",
      "stroke_lon",
      "current_ka"
    ]
  }
]
```

---

### 4.4 Convective Weather Alert Endpoints

#### 9. `GET /api/v1/alerts/active`
- **Description:** Queries Supabase database `alerts` table for all active, unexpired thunderstorm and lightning alerts ordered by latest creation time.
- **Inputs:** None.
- **Downstream Calls:**
  - Synchronous Supabase query: `supabase.table("alerts").select("*").eq("is_active", True).order("created_at", desc=True).limit(50).execute()`.
- **Response Status:** `200 OK`
- **Response Payload Example:**
```json
{
  "timestamp": "2026-09-29T10:30:00.000000+00:00",
  "count": 1,
  "alerts": [
    {
      "alert_id": "7b8417c8-91c6-43e9-92c2-ea396a848a60",
      "city": "Kolkata",
      "latitude": 22.57,
      "longitude": 88.36,
      "alert_type": "thunderstorm",
      "severity": "severe",
      "thunderstorm_probability": 0.72,
      "lightning_probability": 0.65,
      "valid_from": "2026-09-29T10:30:00.000000+00:00",
      "valid_until": "2026-09-29T12:30:00.000000+00:00",
      "lead_time_hours": 1.0,
      "message": "⚠️ SEVERE thunderstorm expected in Kolkata within 1h. Probability: 72%",
      "is_active": true,
      "created_at": "2026-09-29T10:30:01.123456+00:00"
    }
  ]
}
```

---

#### 10. `POST /api/v1/alerts/generate`
- **Description:** Triggers automated batch scan of the 10 major Indian metros. For any city where $P(\text{TS}) \ge \text{ALERT\_PROB\_THRESHOLD}$ ($0.60$), creates an alert, persists it to the Supabase `alerts` table, and returns the list of newly generated alerts.
- **Inputs:** None (HTTP POST).
- **Downstream Calls:**
  1. `NowcastingService.predict_for_cities(INDIAN_CITIES)`.
  2. `AlertService.generate_alerts()` evaluates threshold $\ge 0.60$.
  3. `supabase.table("alerts").insert(alert_dict).execute()`.
- **Response Status:** `200 OK`
- **Response Payload Example:**
```json
{
  "timestamp": "2026-09-29T10:30:00.000000+00:00",
  "alerts_generated": 1,
  "alerts": [
    {
      "alert_id": "7b8417c8-91c6-43e9-92c2-ea396a848a60",
      "city": "Kolkata",
      "latitude": 22.57,
      "longitude": 88.36,
      "alert_type": "thunderstorm",
      "severity": "severe",
      "thunderstorm_probability": 0.72,
      "lightning_probability": 0.65,
      "valid_from": "2026-09-29T10:30:00.000000+00:00",
      "valid_until": "2026-09-29T12:30:00.000000+00:00",
      "lead_time_hours": 1.0,
      "message": "⚠️ SEVERE thunderstorm expected in Kolkata within 1h. Probability: 72%",
      "is_active": true
    }
  ]
}
```

---

## 5. Decision Rules, Severity, & Physical Indices

### 5.1 Storm Severity Classification Rules
The `SeverityClassifier` maps predicted probability and CAPE into operational levels:

$$\text{Severity} = \begin{cases}
\text{None} & \text{if } P(\text{TS}) < 0.15 \\
\text{Very Severe} & \text{if } P(\text{TS}) > 0.85 \land \text{CAPE} > 3500\text{ J/kg} \\
\text{Severe} & \text{if } P(\text{TS}) > 0.65 \land \text{CAPE} > 2500\text{ J/kg} \\
\text{Moderate} & \text{if } P(\text{TS}) > 0.40 \land \text{CAPE} > 1000\text{ J/kg} \\
\text{Weak} & \text{if } P(\text{TS}) \ge 0.15 \\
\text{None} & \text{otherwise}
\end{cases}$$

### 5.2 Lightning Prediction Formulation
The `LightningPredictor` combines the base thunderstorm probability with atmospheric charge-separation proxies:

$$P(\text{LT})_{\text{raw}} = P(\text{TS}) \times 0.7 + \Delta_{\text{CAPE}} + \Delta_{\text{PW}}$$
Where:
- $\Delta_{\text{CAPE}} = +0.20$ if $\text{CAPE} > 2000$, else $+0.10$ if $\text{CAPE} > 1000$, else $0.0$.
- $\Delta_{\text{PW}} = +0.05$ if $\text{PW} > 40\text{ mm}$, else $0.0$.
- $P(\text{LT}) = \min(\max(P(\text{LT})_{\text{raw}}, 0.0), 0.99)$.

### 5.3 Lead-Time Decay Functions
For lead times $\Delta t \ge 0$:
- $\text{Confidence}(\Delta t) = \text{Confidence}_0 \times \max(0.5, 1.0 - 0.08 \cdot \Delta t)$
- $\text{Probability}(\Delta t) = P(\text{TS})_0 \times \max(0.6, 1.0 - 0.05 \cdot \Delta t)$

---

## 6. Verification & Automated Test Status

All 10 endpoints and model execution pathways have been tested via an automated test harness using `fastapi.testclient.TestClient`:

| # | Test Target | Method & Path | Status Code | Result |
|---|---|---|---|---|
| 1 | Health Check | `GET /health` | `200 OK` | Model loaded `True`, threshold `0.1860` |
| 2 | Root Metadata | `GET /` | `200 OK` | Discovered primary endpoints |
| 3 | Nowcast Prediction | `GET /api/v1/predictions/nowcast` | `200 OK` | Computed $0–6\text{h}$ predictions & contributing factors |
| 4 | City Batch Nowcast | `GET /api/v1/predictions/nowcast/cities` | `200 OK` | Parallel predictions for all 10 metros |
| 5 | Historical Replay | `GET /api/v1/predictions/historical` | `200 OK` | Open-Meteo Archive parsed & verified |
| 6 | Current Weather | `GET /api/v1/weather/current` | `200 OK` | Live Open-Meteo JSON payload returned |
| 7 | Instability Indices | `GET /api/v1/weather/indices` | `200 OK` | CAPE & convective potential computed |
| 8 | Sources Status | `GET /api/v1/weather/sources/status` | `200 OK` | 4 data sources probed & reported |
| 9 | Active Alerts | `GET /api/v1/alerts/active` | `200 OK` | Live Supabase table query executed |
| 10 | Alert Generation | `POST /api/v1/alerts/generate` | `200 OK` | Metros evaluated & active alerts inserted |

---

## 7. How to Run the Backend Locally

```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies (if not already installed)
pip install -r requirements.txt

# Start the uvicorn development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Interactive Swagger Documentation:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation:** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 8. Frontend Integration Contract (Alerts & Supabase Realtime)

### Realtime Subscription & Client-Side Filtering
- **RLS Policy Scope:** `public.alerts` allows `SELECT` for `anon` only where `is_active = true`.
- **Realtime Behavior:** When an alert expires or is marked `is_active = false` by the backend, Supabase Realtime will **not** dispatch an update event to `anon` WebSocket subscribers because the row ceases to satisfy the `USING (is_active = true)` RLS policy.
- **Mandatory Frontend Implementation Rules:**
  1. **Client-Side Filtering:** The alert banner and map overlay must filter out alerts where `new Date(alert.valid_until) < new Date()` client-side in the browser.
  2. **Periodic Re-fetch Fallback:** The frontend must poll `GET /api/v1/alerts/active` every 5 minutes (300 seconds) to synchronize the active alerts state and evict stale records.

