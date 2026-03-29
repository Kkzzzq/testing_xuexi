from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime
from typing import Any

import requests

import config.settings as settings
from services.dashboard_hub_service import DashboardHubService
from services.mysql_service import MySQLService
from services.redis_service import RedisService

_METRIC_LINE_RE = re.compile(r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?P<labels>\{[^}]*\})?\s+(?P<value>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)$')

RELEVANT_METRIC_PREFIXES = (
    "dashboard_hub_requests_total",
    "dashboard_hub_request_latency_seconds_count",
    "dashboard_hub_cache_hit_total",
    "dashboard_hub_cache_miss_total",
    "dashboard_hub_summary_source_total",
)

LAYER_BY_OBSERVATION_PREFIX = {
    "obs_db_": "database",
    "obs_cache_": "cache",
    "obs_summary_": "external_dependency_or_ai",
    "obs_http_": "interface",
    "obs_metrics_": "monitoring_or_cache",
    "obs_logs_": "service_execution_path",
    "replay_": "test_or_environment",
}


def _serialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def build_summary_cache_key(dashboard_uid: str) -> str:
    provider = os.getenv("AI_PROVIDER", "deepseek")
    model = os.getenv("AI_MODEL", "deepseek-chat")
    prompt_version = os.getenv("AI_PROMPT_VERSION", "v1")
    return f"dashhub:summary:{dashboard_uid}:{provider}:{model}:{prompt_version}"


def fetch_metrics_text() -> str:
    url = settings.DASHBOARD_HUB_BASE_URL.rstrip("/") + "/metrics"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception:
        return ""


def parse_metrics_snapshot(metrics_text: str) -> dict[str, float]:
    snapshot: dict[str, float] = {}
    for line in metrics_text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _METRIC_LINE_RE.match(line.strip())
        if not match:
            continue
        metric_name = match.group("name")
        if not metric_name.startswith(RELEVANT_METRIC_PREFIXES):
            continue
        labels = match.group("labels") or ""
        value = float(match.group("value"))
        snapshot[f"{metric_name}{labels}"] = value
    return snapshot


def diff_metrics(before: dict[str, float], after: dict[str, float]) -> dict[str, dict[str, float]]:
    diff: dict[str, dict[str, float]] = {}
    for key in sorted(set(before) | set(after)):
        before_value = before.get(key, 0.0)
        after_value = after.get(key, 0.0)
        if math.isclose(before_value, after_value):
            continue
        diff[key] = {
            "before": before_value,
            "after": after_value,
            "delta": after_value - before_value,
        }
    return diff


def collect_metrics_snapshot() -> dict[str, Any]:
    text = fetch_metrics_text()
    return {
        "raw_available": bool(text),
        "parsed": parse_metrics_snapshot(text),
    }


def collect_subscription_snapshot(
    *,
    dashboard_uid: str,
    user_login: str,
    channel: str,
    subscription_id: int | None = None,
) -> dict[str, Any]:
    cache_key = f"dashhub:subscriptions:{dashboard_uid}"
    business_rows = MySQLService.fetch_subscriptions_by_business_key(
        dashboard_uid=dashboard_uid,
        user_login=user_login,
        channel=channel,
    )
    subscription_row = None
    if subscription_id is not None:
        subscription_row = MySQLService.fetch_subscription_by_id(subscription_id)

    return {
        "dashboard_uid": dashboard_uid,
        "user_login": user_login,
        "channel": channel,
        "subscription_id": subscription_id,
        "business_key_count": len(business_rows),
        "business_rows": _serialize(business_rows),
        "subscription_row": _serialize(subscription_row),
        "cache_key": cache_key,
        "cache_exists": RedisService.exists(cache_key),
        "cache_payload": _serialize(RedisService.get_json(cache_key)),
        "cache_ttl": RedisService.ttl(cache_key) if RedisService.exists(cache_key) else None,
    }


def collect_share_link_snapshot(token: str) -> dict[str, Any]:
    cache_key = f"dashhub:share:{token}"
    row = MySQLService.fetch_share_link_by_token(token)
    return {
        "token": token,
        "mysql_row": _serialize(row),
        "cache_key": cache_key,
        "cache_exists": RedisService.exists(cache_key),
        "cache_payload": _serialize(RedisService.get_json(cache_key)),
        "cache_ttl": RedisService.ttl(cache_key) if RedisService.exists(cache_key) else None,
    }


def collect_summary_snapshot(*, dashboard_uid: str, summary_key: str | None = None) -> dict[str, Any]:
    resolved_key = summary_key or build_summary_cache_key(dashboard_uid)
    return {
        "dashboard_uid": dashboard_uid,
        "cache_key": resolved_key,
        "cache_exists": RedisService.exists(resolved_key),
        "cache_payload": _serialize(RedisService.get_json(resolved_key)),
        "cache_ttl": RedisService.ttl(resolved_key) if RedisService.exists(resolved_key) else None,
    }


def collect_service_log_snapshot(*, replay_id: str, limit: int = 200) -> dict[str, Any]:
    try:
        response = DashboardHubService.get_agent_logs(replay_id, limit=limit)
        if response.status_code != 200:
            return {"available": False, "items": []}
        payload = response.json()
        items = payload.get("items", [])
        return {"available": True, "items": _serialize(items)}
    except Exception:
        return {"available": False, "items": []}


def _sanitize_log_item(item: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in item.items():
        if key == "reason" and isinstance(value, str) and "AGENT_DEMO_FAULTS" in value:
            continue
        if isinstance(value, str) and "AGENT_DEMO_FAULTS" in value:
            continue
        sanitized[key] = value
    return sanitized


def derive_likely_layer(observations: list[str], service_logs: list[dict[str, Any]] | None = None) -> str:
    for observation in observations:
        for prefix, layer in LAYER_BY_OBSERVATION_PREFIX.items():
            if observation.startswith(prefix):
                return layer
    if observations:
        return "interface_or_environment"
    if service_logs:
        return "service_execution_path"
    return "not_reproduced_or_environment"


def build_evidence_lines(result: dict[str, Any]) -> list[str]:
    evidence_lines: list[str] = []
    for step in result.get("http_steps", []):
        evidence_lines.append(
            f"HTTP[{step['step']}] status={step['status_code']} expected={step.get('expected_status')} body={step['body_excerpt']}"
        )

    diff = result.get("snapshot", {}).get("diff", {})
    for key, value in diff.items():
        evidence_lines.append(f"SNAPSHOT[{key}] {json.dumps(value, ensure_ascii=False)}")

    for key, value in result.get("intermediate", {}).items():
        evidence_lines.append(f"INTERMEDIATE[{key}] {json.dumps(_serialize(value), ensure_ascii=False)}")

    service_logs = result.get("snapshot", {}).get("after", {}).get("service_logs", {}).get("items", [])
    for raw_log_item in service_logs[-15:]:
        log_item = _sanitize_log_item(raw_log_item)
        evidence_lines.append(f"LOG[{log_item.get('event')}] {json.dumps(_serialize(log_item), ensure_ascii=False)}")

    if not evidence_lines and result.get("observations"):
        evidence_lines.extend([f"OBSERVATION[{item}]" for item in result["observations"]])
    return evidence_lines
