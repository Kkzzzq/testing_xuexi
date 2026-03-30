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
_DEMO_FAULT_MARKER = "AGENT_DEMO_FAULTS"
_DROP = object()

RELEVANT_METRIC_PREFIXES = (
    "dashboard_hub_requests_total",
    "dashboard_hub_request_latency_seconds_count",
    "dashboard_hub_cache_hit_total",
    "dashboard_hub_cache_miss_total",
    "dashboard_hub_summary_source_total",
)

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


def _contains_demo_fault_marker(value: Any) -> bool:
    if isinstance(value, str):
        return _DEMO_FAULT_MARKER in value
    if isinstance(value, dict):
        return any(_contains_demo_fault_marker(key) or _contains_demo_fault_marker(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_demo_fault_marker(item) for item in value)
    return False


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        if _DEMO_FAULT_MARKER in value:
            return _DROP
        return value

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if _contains_demo_fault_marker(key):
                continue
            sanitized_item = _sanitize_value(item)
            if sanitized_item is _DROP:
                continue
            sanitized[str(key)] = sanitized_item
        return sanitized

    if isinstance(value, list):
        sanitized_list = []
        for item in value:
            sanitized_item = _sanitize_value(item)
            if sanitized_item is _DROP:
                continue
            sanitized_list.append(sanitized_item)
        return sanitized_list

    if isinstance(value, tuple):
        sanitized_tuple = []
        for item in value:
            sanitized_item = _sanitize_value(item)
            if sanitized_item is _DROP:
                continue
            sanitized_tuple.append(sanitized_item)
        return sanitized_tuple

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

    cache_exists = RedisService.exists(cache_key)
    return {
        "dashboard_uid": dashboard_uid,
        "user_login": user_login,
        "channel": channel,
        "subscription_id": subscription_id,
        "business_key_count": len(business_rows),
        "business_rows": _serialize(business_rows),
        "subscription_row": _serialize(subscription_row),
        "cache_key": cache_key,
        "cache_exists": cache_exists,
        "cache_payload": _serialize(RedisService.get_json(cache_key)),
        "cache_ttl": RedisService.ttl(cache_key) if cache_exists else None,
    }


def collect_share_link_snapshot(token: str) -> dict[str, Any]:
    cache_key = f"dashhub:share:{token}"
    row = MySQLService.fetch_share_link_by_token(token)
    cache_exists = RedisService.exists(cache_key)
    return {
        "token": token,
        "mysql_row": _serialize(row),
        "cache_key": cache_key,
        "cache_exists": cache_exists,
        "cache_payload": _serialize(RedisService.get_json(cache_key)),
        "cache_ttl": RedisService.ttl(cache_key) if cache_exists else None,
    }


def collect_summary_snapshot(*, dashboard_uid: str, summary_key: str | None = None) -> dict[str, Any]:
    resolved_key = summary_key or build_summary_cache_key(dashboard_uid)
    cache_exists = RedisService.exists(resolved_key)
    return {
        "dashboard_uid": dashboard_uid,
        "cache_key": resolved_key,
        "cache_exists": cache_exists,
        "cache_payload": _serialize(RedisService.get_json(resolved_key)),
        "cache_ttl": RedisService.ttl(resolved_key) if cache_exists else None,
    }


def collect_service_log_snapshot(*, replay_id: str, limit: int = 200) -> dict[str, Any]:
    try:
        response = DashboardHubService.get_agent_logs(replay_id, limit=limit)
        if response.status_code != 200:
            return {"available": False, "items": []}
        payload = response.json()
        items = payload.get("items", [])
        sanitized_items = _sanitize_value(_serialize(items))
        return {
            "available": True,
            "items": [] if sanitized_items is _DROP else sanitized_items,
        }
    except Exception:
        return {"available": False, "items": []}


def _sanitize_log_item(item: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_value(item)
    if sanitized is _DROP or not isinstance(sanitized, dict):
        return {}
    return sanitized


def build_evidence_lines(result: dict[str, Any]) -> list[str]:
    evidence_lines: list[str] = []

    state = result.get("state") or {}
    if state.get("replay_status"):
        evidence_lines.append(f"STATE[replay_status]={state['replay_status']}")
    if result.get("chain_status"):
        evidence_lines.append(f"STATE[chain_status]={result['chain_status']}")
    if result.get("first_abnormal_stage"):
        evidence_lines.append(f"STATE[first_abnormal_stage]={result['first_abnormal_stage']}")
    if result.get("suspected_segment"):
        evidence_lines.append(f"STATE[suspected_segment]={result['suspected_segment']}")

    for step in result.get("http_steps", []):
        line = (
            f"HTTP[{step['step']}] status={step['status_code']} expected={step.get('expected_status')} body={step['body_excerpt']}"
        )
        if not _contains_demo_fault_marker(line):
            evidence_lines.append(line)

    facts = result.get("facts", {}) or {}
    for key in sorted(facts):
        value = facts[key]
        if value is None:
            continue
        serialized = json.dumps(_serialize(value), ensure_ascii=False)
        if not _contains_demo_fault_marker(serialized):
            evidence_lines.append(f"FACT[{key}]={serialized}")

    stage_results = result.get("stage_results", {}) or {}
    for key in sorted(stage_results):
        serialized = json.dumps(_serialize(stage_results[key]), ensure_ascii=False)
        if not _contains_demo_fault_marker(serialized):
            evidence_lines.append(f"STAGE[{key}]={serialized}")

    diff = result.get("snapshot", {}).get("diff", {})
    for key, value in diff.items():
        serialized = json.dumps(_serialize(value), ensure_ascii=False)
        if not _contains_demo_fault_marker(serialized):
            evidence_lines.append(f"SNAPSHOT[{key}] {serialized}")

    for key, value in result.get("intermediate", {}).items():
        sanitized_value = _sanitize_value(_serialize(value))
        if sanitized_value is _DROP:
            continue
        serialized = json.dumps(sanitized_value, ensure_ascii=False)
        if not _contains_demo_fault_marker(serialized):
            evidence_lines.append(f"INTERMEDIATE[{key}] {serialized}")

    service_logs = result.get("snapshot", {}).get("after", {}).get("service_logs", {}).get("items", [])
    for raw_log_item in service_logs[-15:]:
        log_item = _sanitize_log_item(raw_log_item)
        if not log_item:
            continue
        serialized = json.dumps(_serialize(log_item), ensure_ascii=False)
        if not _contains_demo_fault_marker(serialized):
            evidence_lines.append(f"LOG[{log_item.get('event')}] {serialized}")

    return evidence_lines

