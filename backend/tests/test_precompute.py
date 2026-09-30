"""Unit and integration tests for precompute script and CDN artifact publishing."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from scripts.precompute import run_precomputation


from datetime import datetime, timedelta, timezone

@pytest.fixture
def mock_open_meteo_batch():
    """Generates realistic Open-Meteo responses for grid & cities batch fetches."""
    def _create_response(num_points=1):
        base_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        time_arr = [
            (base_time + timedelta(hours=h - 24)).strftime("%Y-%m-%dT%H:00")
            for h in range(72)
        ]
        single_payload = {
            "latitude": 28.5,
            "longitude": 77.25,
            "utc_offset_seconds": 19800,
            "timezone": "Asia/Kolkata",
            "current": {
                "temperature_2m": 30.0,
                "relative_humidity_2m": 65.0,
                "dew_point_2m": 22.0,
                "surface_pressure": 1002.0,
                "wind_speed_10m": 5.0,
                "wind_direction_10m": 120,
                "cloud_cover": 50,
                "precipitation": 0.0,
                "weather_code": 1,
            },
            "hourly": {
                "time": time_arr,
                "temperature_2m": [30.0] * 72,
                "relative_humidity_2m": [65.0] * 72,
                "dew_point_2m": [22.0] * 72,
                "surface_pressure": [1002.0] * 72,
                "wind_speed_10m": [5.0] * 72,
                "wind_direction_10m": [120] * 72,
                "cloud_cover": [50] * 72,
                "precipitation": [0.0] * 72,
                "precipitation_probability": [10] * 72,
                "cape": [2000.0] * 72,
                "convective_inhibition": [-20.0] * 72,
                "total_column_integrated_water_vapour": [45.0] * 72,
                "weather_code": [1] * 72,
            },
        }
        if num_points == 1:
            return [single_payload]
        return [single_payload for _ in range(num_points)]
    return _create_response


@pytest.mark.asyncio
async def test_run_precomputation_with_backend_post(tmp_path: Path, mock_open_meteo_batch):
    """
    Test run_precomputation end-to-end:
    - Mocks Open-Meteo
    - Mocks backend /health and /alerts/generate
    - Asserts 3 files written
    - Asserts alerts POST is made with X-Admin-Token header and valid JSON
    """
    grid_points_count = 70  # Standard India land mask points
    cities_count = 10

    async def mock_fetch_weather(client, points):
        return mock_open_meteo_batch(len(points))

    captured_requests = []

    async def mock_httpx_get(self, url, **kwargs):
        if "/health" in str(url):
            return httpx.Response(200, json={"status": "healthy"}, request=httpx.Request("GET", str(url)))
        return httpx.Response(200, json={}, request=httpx.Request("GET", str(url)))

    async def mock_httpx_post(self, url, **kwargs):
        captured_requests.append({
            "url": str(url),
            "headers": kwargs.get("headers", {}),
            "json": kwargs.get("json", {}),
        })
        return httpx.Response(
            200,
            json={"status": "success", "alerts_generated": 0, "alerts": []},
            request=httpx.Request("POST", str(url)),
        )

    with patch("scripts.precompute.fetch_batch_weather", side_effect=mock_fetch_weather), \
         patch("httpx.AsyncClient.get", new=mock_httpx_get), \
         patch("httpx.AsyncClient.post", new=mock_httpx_post):

        success = await run_precomputation(
            output_dir=tmp_path,
            backend_url="https://api.vajranowcast.test",
            admin_token="secret_admin_token_123",
        )

    assert success is True

    # 1. Check all 3 files exist and are valid JSON
    grid_file = tmp_path / "grid_latest.json"
    cities_file = tmp_path / "cities_latest.json"
    alerts_file = tmp_path / "alerts_latest.json"

    assert grid_file.exists()
    assert cities_file.exists()
    assert alerts_file.exists()

    grid_data = json.loads(grid_file.read_text(encoding="utf-8"))
    cities_data = json.loads(cities_file.read_text(encoding="utf-8"))
    alerts_data = json.loads(alerts_file.read_text(encoding="utf-8"))

    assert "points" in grid_data
    assert len(grid_data["points"]) > 0
    assert "cities" in cities_data
    assert len(cities_data["cities"]) == 10
    assert "alerts" in alerts_data

    # 2. Check alert generation POST was sent
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert "https://api.vajranowcast.test/api/v1/alerts/generate" in req["url"]
    assert req["headers"].get("X-Admin-Token") == "secret_admin_token_123"
    assert "cities" in req["json"]
    assert len(req["json"]["cities"]) == 10


@pytest.mark.asyncio
async def test_run_precomputation_no_backend_args(tmp_path: Path, mock_open_meteo_batch):
    """
    Test run_precomputation with no backend args:
    - Files are written
    - No backend network calls are attempted
    - Exits 0 / returns True
    """
    async def mock_fetch_weather(client, points):
        return mock_open_meteo_batch(len(points))

    captured_requests = []

    async def mock_httpx_post(self, url, **kwargs):
        captured_requests.append(str(url))
        return httpx.Response(200, json={}, request=httpx.Request("POST", str(url)))

    with patch("scripts.precompute.fetch_batch_weather", side_effect=mock_fetch_weather), \
         patch("httpx.AsyncClient.post", new=mock_httpx_post):

        success = await run_precomputation(
            output_dir=tmp_path,
            backend_url=None,
            admin_token=None,
        )

    assert success is True
    assert (tmp_path / "grid_latest.json").exists()
    assert (tmp_path / "cities_latest.json").exists()
    assert (tmp_path / "alerts_latest.json").exists()
    assert len(captured_requests) == 0


@pytest.mark.asyncio
async def test_run_precomputation_resilient_to_backend_failure(tmp_path: Path, mock_open_meteo_batch):
    """
    Test that a backend health check failure or alert post failure
    does NOT fail run_precomputation or block writing files.
    """
    async def mock_fetch_weather(client, points):
        return mock_open_meteo_batch(len(points))

    async def mock_httpx_get(self, url, **kwargs):
        # Backend health is down
        return httpx.Response(503, json={"detail": "Service Unavailable"}, request=httpx.Request("GET", str(url)))

    with patch("scripts.precompute.fetch_batch_weather", side_effect=mock_fetch_weather), \
         patch("httpx.AsyncClient.get", new=mock_httpx_get), \
         patch("asyncio.sleep", new_callable=AsyncMock):  # Speed up retries

        success = await run_precomputation(
            output_dir=tmp_path,
            backend_url="https://api.vajranowcast.test",
            admin_token="secret_admin_token_123",
        )

    # Must still return True since files were written successfully
    assert success is True
    assert (tmp_path / "grid_latest.json").exists()
    assert (tmp_path / "cities_latest.json").exists()
    assert (tmp_path / "alerts_latest.json").exists()
