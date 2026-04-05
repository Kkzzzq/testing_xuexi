from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from services.dashboard_hub_service import DashboardHubService


def _parse_metric_labels(raw_labels: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not raw_labels:
        return labels

    for item in raw_labels.split(','):
        item = item.strip()
        if not item or '=' not in item:
            continue
        key, raw_value = item.split('=', 1)
        labels[key.strip()] = raw_value.strip().strip('"')
    return labels


def _parse_metrics(text: str) -> list[tuple[str, dict[str, str], float]]:
    metrics: list[tuple[str, dict[str, str], float]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        if '{' in line and '}' in line:
            metric_name, remainder = line.split('{', 1)
            labels_raw, value_raw = remainder.split('}', 1)
            labels = _parse_metric_labels(labels_raw)
            value = float(value_raw.strip())
        else:
            metric_name, value_raw = line.split(None, 1)
            labels = {}
            value = float(value_raw.strip())

        metrics.append((metric_name, labels, value))
    return metrics


def _metric_value(metrics: list[tuple[str, dict[str, str], float]], name: str, labels: dict[str, str] | None = None) -> float:
    expected = labels or {}
    total = 0.0
    for metric_name, metric_labels, value in metrics:
        if metric_name != name:
            continue
        if all(metric_labels.get(key) == expected_value for key, expected_value in expected.items()):
            total += value
    return total


@pytest.mark.metrics
def test_metrics_include_internal_dependency_and_business_indicators(session_context):
    unique_user_login = f"{session_context.existing_user_login}-metrics-{uuid4().hex[:8]}"

    create_response, subscription_id = DashboardHubService.create_subscription(
        dashboard_uid=session_context.dashboard_uid,
        user_login=unique_user_login,
        channel='email',
    )
    assert create_response.status_code == 201
    session_context.register_subscription(subscription_id)

    conflict_response, _ = DashboardHubService.create_subscription(
        dashboard_uid=session_context.dashboard_uid,
        user_login=unique_user_login,
        channel='email',
    )
    assert conflict_response.status_code == 409

    first_list_response = DashboardHubService.list_subscriptions(session_context.dashboard_uid)
    assert first_list_response.status_code == 200

    second_list_response = DashboardHubService.list_subscriptions(session_context.dashboard_uid)
    assert second_list_response.status_code == 200

    share_response, token = DashboardHubService.create_share_link(
        session_context.dashboard_uid,
        expire_at=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )
    assert share_response.status_code == 201
    session_context.register_share_token(token)

    read_response = DashboardHubService.get_share_link(token)
    assert read_response.status_code == 200

    metrics_response = DashboardHubService.get_metrics()
    assert metrics_response.status_code == 200
    metrics = _parse_metrics(metrics_response.text)

    assert _metric_value(
        metrics,
        'dashboard_hub_grafana_requests_total',
        {'endpoint': 'dashboard_by_uid', 'status': '200'},
    ) >= 1
    assert _metric_value(
        metrics,
        'dashboard_hub_subscription_conflicts_total',
        {'channel': 'email'},
    ) >= 1
    assert _metric_value(
        metrics,
        'dashboard_hub_cache_invalidations_total',
        {'cache_name': 'subscriptions', 'reason': 'subscription_create'},
    ) >= 1
    assert _metric_value(
        metrics,
        'dashboard_hub_cache_hit_total',
        {'cache_name': 'subscriptions'},
    ) >= 1
    assert _metric_value(
        metrics,
        'dashboard_hub_cache_miss_total',
        {'cache_name': 'subscriptions'},
    ) >= 1
    assert _metric_value(
        metrics,
        'dashboard_hub_cache_hit_total',
        {'cache_name': 'dashboard_exists'},
    ) >= 1
    assert _metric_value(
        metrics,
        'dashboard_hub_cache_miss_total',
        {'cache_name': 'dashboard_exists'},
    ) >= 1
    assert _metric_value(
        metrics,
        'dashboard_hub_db_operation_latency_seconds_count',
        {'operation': 'subscription_create_commit'},
    ) >= 1
    assert _metric_value(
        metrics,
        'dashboard_hub_cache_operation_latency_seconds_count',
        {'operation': 'get', 'cache_name': 'subscriptions'},
    ) >= 1


@pytest.mark.metrics
def test_expired_share_link_metric_is_exposed(session_context):
    create_response, token = DashboardHubService.create_share_link(
        session_context.dashboard_uid,
        expire_at=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
    )
    assert create_response.status_code == 201
    session_context.register_share_token(token)

    read_response = DashboardHubService.get_share_link(token)
    assert read_response.status_code == 410

    metrics_response = DashboardHubService.get_metrics()
    assert metrics_response.status_code == 200
    metrics = _parse_metrics(metrics_response.text)

    assert _metric_value(
        metrics,
        'dashboard_hub_share_link_expired_total',
        {'source': 'cache'},
    ) >= 1 or _metric_value(
        metrics,
        'dashboard_hub_share_link_expired_total',
        {'source': 'db'},
    ) >= 1
