from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response


REQUEST_COUNT = Counter("dashboard_hub_requests_total", "Total HTTP requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("dashboard_hub_request_latency_seconds", "HTTP latency", ["method", "path"])


def metrics_response():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
