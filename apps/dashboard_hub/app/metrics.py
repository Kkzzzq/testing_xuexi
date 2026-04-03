from __future__ import annotations

import re
from contextlib import contextmanager
from time import perf_counter

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response


REQUEST_COUNT = Counter(
    "dashboard_hub_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "dashboard_hub_request_latency_seconds",
    "HTTP latency",
    ["method", "path"],
)
CACHE_HIT_COUNT = Counter(
    "dashboard_hub_cache_hit_total",
    "Total cache hit count",
    ["cache_name"],
)
CACHE_MISS_COUNT = Counter(
    "dashboard_hub_cache_miss_total",
    "Total cache miss count",
    ["cache_name"],
)
SUMMARY_SOURCE_COUNT = Counter(
    "dashboard_hub_summary_source_total",
    "Total dashboard summary source count",
    ["source"],
)

GRAFANA_REQUEST_COUNT = Counter(
    "dashboard_hub_grafana_requests_total",
    "Total outbound Grafana API requests",
    ["endpoint", "status"],
)
GRAFANA_REQUEST_LATENCY = Histogram(
    "dashboard_hub_grafana_request_latency_seconds",
    "Latency of outbound Grafana API requests",
    ["endpoint"],
)
GRAFANA_REQUEST_FAILURE_COUNT = Counter(
    "dashboard_hub_grafana_request_failures_total",
    "Total failed outbound Grafana API requests",
    ["endpoint", "reason"],
)
DB_OPERATION_LATENCY = Histogram(
    "dashboard_hub_db_operation_latency_seconds",
    "Latency of database operations",
    ["operation"],
)
CACHE_OPERATION_LATENCY = Histogram(
    "dashboard_hub_cache_operation_latency_seconds",
    "Latency of cache operations",
    ["operation", "cache_name"],
)
SUBSCRIPTION_CONFLICT_COUNT = Counter(
    "dashboard_hub_subscription_conflicts_total",
    "Total subscription create conflicts",
    ["channel"],
)
SHARE_LINK_EXPIRED_COUNT = Counter(
    "dashboard_hub_share_link_expired_total",
    "Total expired share-link reads",
    ["source"],
)
CACHE_INVALIDATION_COUNT = Counter(
    "dashboard_hub_cache_invalidations_total",
    "Total cache invalidations triggered by write operations",
    ["cache_name", "reason"],
)

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
_INT_RE = re.compile(r"^\d+$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]{16,}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,}$")

_STATIC_SEGMENTS = {
    "api",
    "v1",
    "health",
    "metrics",
    "dashboards",
    "subscriptions",
    "share-links",
    "summary",
}


def _looks_like_share_token(segment: str) -> bool:
    return bool(_TOKEN_RE.fullmatch(segment) or _UUID_RE.fullmatch(segment) or _HEX_RE.fullmatch(segment))


def normalize_metrics_path(request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path

    raw_path = request.url.path.strip("/")
    if not raw_path:
        return "/"

    segments = raw_path.split("/")
    normalized: list[str] = []

    for index, segment in enumerate(segments):
        previous = segments[index - 1] if index > 0 else None

        if segment in _STATIC_SEGMENTS:
            normalized.append(segment)
            continue

        if previous == "dashboards":
            normalized.append("{dashboard_uid}")
            continue

        if previous == "subscriptions" and _INT_RE.fullmatch(segment):
            normalized.append("{subscription_id}")
            continue

        if previous == "share-links" and _looks_like_share_token(segment):
            normalized.append("{token}")
            continue

        if _UUID_RE.fullmatch(segment):
            normalized.append("{uuid}")
            continue

        if _INT_RE.fullmatch(segment):
            normalized.append("{id}")
            continue

        normalized.append(segment)

    return "/" + "/".join(normalized)


@contextmanager
def observe_histogram(histogram: Histogram, *labels: str):
    start = perf_counter()
    try:
        yield
    finally:
        histogram.labels(*labels).observe(perf_counter() - start)


def metrics_response():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
