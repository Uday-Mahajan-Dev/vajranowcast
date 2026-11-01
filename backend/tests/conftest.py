"""Test configuration, in-memory Supabase fake, and safety isolation guards for VajraNowcast."""

from datetime import datetime, timezone
import os
import socket
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

# Ensure backend directory is on Python path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Real production identifiers for safety assertions
REAL_PROD_HOST = "nfhvwyldjmpwvrduuzqc.supabase.co"
REAL_PROD_SUPABASE_URL = f"https://{REAL_PROD_HOST}"

# Dummy values for test isolation
DUMMY_SUPABASE_URL = "https://mock-test-isolation.invalid"
DUMMY_SERVICE_ROLE_KEY = "mock-service-role-key-test-isolation"
DUMMY_ANON_KEY = "mock-anon-key-test-isolation"
DUMMY_JWT_SECRET = "mock-jwt-secret-test-isolation-at-least-32-chars-long"

# 3. Set SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY to dummy values in the test environment
os.environ["SUPABASE_URL"] = DUMMY_SUPABASE_URL
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = DUMMY_SERVICE_ROLE_KEY
os.environ["SUPABASE_ANON_KEY"] = DUMMY_ANON_KEY

# Also sync settings if imported
from app.config import settings

settings.SUPABASE_URL = DUMMY_SUPABASE_URL
settings.SUPABASE_SERVICE_ROLE_KEY = DUMMY_SERVICE_ROLE_KEY
settings.SUPABASE_ANON_KEY = DUMMY_ANON_KEY


# 2. Safety Guard: Fail loudly if a real SUPABASE_URL is used for an insert/update/delete
def check_supabase_safety_guard(operation: str, client_url: Optional[str] = None):
    """Guard against any write operation directed at the production Supabase database."""
    urls_to_inspect = [
        client_url,
        getattr(settings, "SUPABASE_URL", None),
        os.environ.get("SUPABASE_URL"),
    ]
    for url in urls_to_inspect:
        if not url:
            continue
        u = str(url).lower()
        if REAL_PROD_HOST in u or (
            "supabase.co" in u
            and "mock" not in u
            and "test" not in u
            and "invalid" not in u
        ):
            pytest.fail(
                f"SAFETY GUARD TRIGGERED: Real production Supabase URL ({url}) detected during {operation.upper()}! "
                f"All tests must write exclusively to the in-memory fake store.",
                pytrace=True,
            )


# Network Safety Guard: Block and record any DNS or HTTP attempt to the real Supabase host
_orig_getaddrinfo = socket.getaddrinfo


def _guarded_getaddrinfo(host, *args, **kwargs):
    if host and isinstance(host, str):
        h = host.lower()
        if REAL_PROD_HOST in h or (
            "supabase.co" in h
            and "mock" not in h
            and "test" not in h
            and "invalid" not in h
        ):
            pytest.fail(
                f"NETWORK SAFETY GUARD: DNS resolution to real Supabase host '{host}' attempted during test execution!",
                pytrace=True,
            )
    return _orig_getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _guarded_getaddrinfo


# Guard real Postgrest write methods if postgrest is imported
try:
    import postgrest._sync.request_builder as prb

    def _guarded_postgrest_insert(self, *args, **kwargs):
        pytest.fail(
            "SAFETY GUARD: Real Postgrest insert() invoked in test environment! Tests must use in-memory fake.",
            pytrace=True,
        )

    def _guarded_postgrest_update(self, *args, **kwargs):
        pytest.fail(
            "SAFETY GUARD: Real Postgrest update() invoked in test environment! Tests must use in-memory fake.",
            pytrace=True,
        )

    def _guarded_postgrest_delete(self, *args, **kwargs):
        pytest.fail(
            "SAFETY GUARD: Real Postgrest delete() invoked in test environment! Tests must use in-memory fake.",
            pytrace=True,
        )

    prb.SyncRequestBuilder.insert = _guarded_postgrest_insert
    prb.SyncRequestBuilder.update = _guarded_postgrest_update
    prb.SyncRequestBuilder.delete = _guarded_postgrest_delete
except Exception:
    pass


# Guard real httpx Client and AsyncClient send methods against real Supabase host
try:
    import httpx

    _orig_client_send = httpx.Client.send
    _orig_async_client_send = httpx.AsyncClient.send

    def _guarded_client_send(self, request, *args, **kwargs):
        host = getattr(request.url, "host", "") or ""
        if REAL_PROD_HOST in host.lower() or (
            "supabase.co" in host.lower()
            and "mock" not in host.lower()
            and "test" not in host.lower()
        ):
            pytest.fail(
                f"HTTP SAFETY GUARD: Real Supabase HTTP request blocked: {request.url}",
                pytrace=True,
            )
        return _orig_client_send(self, request, *args, **kwargs)

    async def _guarded_async_client_send(self, request, *args, **kwargs):
        host = getattr(request.url, "host", "") or ""
        if REAL_PROD_HOST in host.lower() or (
            "supabase.co" in host.lower()
            and "mock" not in host.lower()
            and "test" not in host.lower()
        ):
            pytest.fail(
                f"HTTP SAFETY GUARD: Real Supabase HTTP async request blocked: {request.url}",
                pytrace=True,
            )
        return await _orig_async_client_send(self, request, *args, **kwargs)

    httpx.Client.send = _guarded_client_send
    httpx.AsyncClient.send = _guarded_async_client_send
except Exception:
    pass


# In-Memory Fake Postgrest and Supabase Implementation
class FakePostgrestResponse:
    """Mock response object mirroring Postgrest APIResponse."""

    def __init__(self, data: Optional[Any] = None, count: Optional[int] = None):
        self.data = data if data is not None else []
        self.count = count if count is not None else (len(self.data) if isinstance(self.data, list) else 1)


class FakeQueryBuilder:
    """In-memory query builder supporting table chaining, filters, and mutations."""

    def __init__(self, table_name: str, store: Dict[str, List[Dict[str, Any]]], client: "FakeSupabaseClient"):
        self.table_name = table_name
        self.store = store
        self.client = client
        self._op = "select"
        self._columns = "*"
        self._count_mode = None
        self._insert_data: List[Dict[str, Any]] = []
        self._update_data: Dict[str, Any] = {}
        self._filters: List[tuple] = []
        self._order_by: Optional[str] = None
        self._order_desc: bool = False
        self._limit: Optional[int] = None
        self._single: bool = False
        self._maybe_single: bool = False

    def select(self, columns: str = "*", count: Optional[str] = None):
        self._op = "select"
        self._columns = columns
        self._count_mode = count
        return self

    def insert(self, record_or_records: Any, *args, **kwargs):
        self.client.check_write_safety("insert", self.table_name)
        self._op = "insert"
        if isinstance(record_or_records, list):
            self._insert_data = [dict(r) for r in record_or_records]
        elif isinstance(record_or_records, dict):
            self._insert_data = [dict(record_or_records)]
        else:
            self._insert_data = [record_or_records]
        return self

    def upsert(self, record_or_records: Any, *args, **kwargs):
        return self.insert(record_or_records, *args, **kwargs)

    def update(self, updates: Dict[str, Any], *args, **kwargs):
        self.client.check_write_safety("update", self.table_name)
        self._op = "update"
        self._update_data = dict(updates)
        return self

    def delete(self, *args, **kwargs):
        self.client.check_write_safety("delete", self.table_name)
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any):
        self._filters.append((column, "eq", value))
        return self

    def neq(self, column: str, value: Any):
        self._filters.append((column, "neq", value))
        return self

    def lt(self, column: str, value: Any):
        self._filters.append((column, "lt", value))
        return self

    def lte(self, column: str, value: Any):
        self._filters.append((column, "lte", value))
        return self

    def gt(self, column: str, value: Any):
        self._filters.append((column, "gt", value))
        return self

    def gte(self, column: str, value: Any):
        self._filters.append((column, "gte", value))
        return self

    def in_(self, column: str, values: List[Any]):
        self._filters.append((column, "in", set(values)))
        return self

    def order(self, column: str, desc: bool = False):
        self._order_by = column
        self._order_desc = desc
        return self

    def limit(self, count: int):
        self._limit = count
        return self

    def single(self):
        self._single = True
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def _matches_filters(self, row: Dict[str, Any]) -> bool:
        for col, op, val in self._filters:
            row_val = row.get(col)
            if op == "eq":
                if row_val != val:
                    return False
            elif op == "neq":
                if row_val == val:
                    return False
            elif op == "in":
                if row_val not in val:
                    return False
            elif op == "lt":
                if row_val is None or str(row_val) >= str(val):
                    return False
            elif op == "lte":
                if row_val is None or str(row_val) > str(val):
                    return False
            elif op == "gt":
                if row_val is None or str(row_val) <= str(val):
                    return False
            elif op == "gte":
                if row_val is None or str(row_val) < str(val):
                    return False
        return True

    def execute(self) -> FakePostgrestResponse:
        table_rows = self.store.setdefault(self.table_name, [])

        if self._op == "insert":
            inserted = []
            for item in self._insert_data:
                row = dict(item)
                if "created_at" not in row:
                    row["created_at"] = datetime.now(timezone.utc).isoformat()
                table_rows.append(row)
                inserted.append(row)
            data: Any = inserted[0] if (self._single or self._maybe_single) and inserted else inserted
            return FakePostgrestResponse(data=data, count=len(inserted))

        elif self._op == "update":
            updated = []
            for row in table_rows:
                if self._matches_filters(row):
                    row.update(self._update_data)
                    updated.append(row)
            data = updated[0] if (self._single or self._maybe_single) and updated else updated
            return FakePostgrestResponse(data=data, count=len(updated))

        elif self._op == "delete":
            kept = []
            deleted = []
            for row in table_rows:
                if self._matches_filters(row):
                    deleted.append(row)
                else:
                    kept.append(row)
            self.store[self.table_name] = kept
            return FakePostgrestResponse(data=deleted, count=len(deleted))

        elif self._op == "select":
            matched = [row for row in table_rows if self._matches_filters(row)]
            if self._order_by:
                matched.sort(
                    key=lambda r: (r.get(self._order_by) is not None, r.get(self._order_by)),
                    reverse=self._order_desc,
                )
            total_count = len(matched)
            if self._limit is not None:
                matched = matched[: self._limit]

            if self._single:
                data = dict(matched[0]) if matched else None
            elif self._maybe_single:
                data = dict(matched[0]) if matched else None
            else:
                data = [dict(r) for r in matched]

            return FakePostgrestResponse(data=data, count=total_count)

        return FakePostgrestResponse(data=[], count=0)


class FakeSupabaseClient:
    """In-memory Supabase client replacement for test isolation."""

    def __init__(self, url: str = DUMMY_SUPABASE_URL, key: str = DUMMY_SERVICE_ROLE_KEY):
        self.url = url
        self.key = key
        self.store: Dict[str, List[Dict[str, Any]]] = {
            "alerts": [],
            "predictions": [],
            "weather_cache": [],
        }
        self.auth = MagicMock()
        self.auth.admin = MagicMock()
        self.storage = MagicMock()

    def table(self, table_name: str) -> FakeQueryBuilder:
        return FakeQueryBuilder(table_name, self.store, self)

    def from_(self, table_name: str) -> FakeQueryBuilder:
        return self.table(table_name)

    def rpc(self, fn: str, params: Optional[Dict[str, Any]] = None):
        builder = MagicMock()
        builder.execute.return_value = FakePostgrestResponse(data=None)
        return builder

    def check_write_safety(self, operation: str, table_name: str):
        check_supabase_safety_guard(operation, self.url)


# 1. Autouse fixture replacing Supabase client with in-memory fake for EVERY test
@pytest.fixture(autouse=True)
def fake_supabase(monkeypatch):
    """
    Autouse fixture that provides an isolated in-memory Supabase fake for every test.
    Ensures no test ever contacts or writes to the real Supabase project.
    """
    fake_client = FakeSupabaseClient(url=DUMMY_SUPABASE_URL, key=DUMMY_SERVICE_ROLE_KEY)

    # Enforce dummy configurations
    monkeypatch.setattr(settings, "SUPABASE_URL", DUMMY_SUPABASE_URL)
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", DUMMY_SERVICE_ROLE_KEY)
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", DUMMY_ANON_KEY)

    # Patch client getters and factories across the application
    monkeypatch.setattr("app.models.database.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.models.database.get_supabase_admin", lambda: fake_client)
    monkeypatch.setattr("app.services.alert_service.get_supabase_admin", lambda: fake_client)
    monkeypatch.setattr("scripts.supabase_maintenance.get_supabase_admin", lambda: fake_client)

    try:
        import supabase

        monkeypatch.setattr(supabase, "create_client", lambda *args, **kwargs: fake_client)
    except ImportError:
        pass

    try:
        import app.models.database as db_module

        monkeypatch.setattr(db_module, "create_client", lambda *args, **kwargs: fake_client)
    except (ImportError, AttributeError):
        pass

    yield fake_client
