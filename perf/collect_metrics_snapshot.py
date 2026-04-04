from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TARGET_METRICS = (
    'dashboard_hub_requests_total',
    'dashboard_hub_request_latency_seconds_sum',
    'dashboard_hub_request_latency_seconds_count',
    'dashboard_hub_requests_in_progress',
    'dashboard_hub_request_exceptions_total',
    'dashboard_hub_cache_hit_total',
    'dashboard_hub_cache_miss_total',
    'dashboard_hub_cache_invalidations_total',
    'dashboard_hub_cache_operation_latency_seconds_sum',
    'dashboard_hub_cache_operation_latency_seconds_count',
    'dashboard_hub_db_operation_latency_seconds_sum',
    'dashboard_hub_db_operation_latency_seconds_count',
    'dashboard_hub_grafana_requests_total',
    'dashboard_hub_grafana_request_failures_total',
    'dashboard_hub_grafana_request_latency_seconds_sum',
    'dashboard_hub_grafana_request_latency_seconds_count',
    'dashboard_hub_subscription_conflicts_total',
    'dashboard_hub_share_link_expired_total',
    'dashboard_hub_summary_source_total',
)

_METRIC_NAME_RE = re.compile(r'^[a-zA-Z_:][a-zA-Z0-9_:]*$')
_LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def _parse_labels(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    return {key: value.encode('utf-8').decode('unicode_escape') for key, value in _LABEL_RE.findall(raw)}


def _fetch_metrics_text(metrics_url: str) -> str:
    with urllib.request.urlopen(metrics_url, timeout=10) as response:
        return response.read().decode('utf-8')


def _split_metric_line(line: str) -> tuple[str, str | None, float] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return None

    try:
        metric_part, value_part = stripped.rsplit(None, 1)
    except ValueError:
        return None

    try:
        value = float(value_part)
    except ValueError:
        return None

    if '{' not in metric_part:
        if not _METRIC_NAME_RE.fullmatch(metric_part):
            return None
        return metric_part, None, value

    brace_start = metric_part.find('{')
    if brace_start <= 0 or not metric_part.endswith('}'):
        return None

    name = metric_part[:brace_start]
    if not _METRIC_NAME_RE.fullmatch(name):
        return None

    labels = metric_part[brace_start + 1 : -1]
    return name, labels, value



def _parse_metrics(text: str) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for line in text.splitlines():
        parsed = _split_metric_line(line)
        if parsed is None:
            continue
        name, raw_labels, value = parsed
        if name not in TARGET_METRICS:
            continue
        samples.append(
            {
                'name': name,
                'labels': _parse_labels(raw_labels),
                'value': value,
            }
        )
    return samples


def _round_ms(seconds: float) -> float:
    return round(seconds * 1000.0, 3)


def build_snapshot(metrics_url: str) -> dict[str, Any]:
    text = _fetch_metrics_text(metrics_url)
    samples = _parse_metrics(text)

    request_total = 0.0
    request_by_path_status: dict[str, float] = defaultdict(float)
    request_by_status_family: dict[str, float] = defaultdict(float)
    request_latency_sum: dict[str, float] = defaultdict(float)
    request_latency_count: dict[str, float] = defaultdict(float)
    inflight_by_path: dict[str, float] = defaultdict(float)
    exception_by_path: dict[str, float] = defaultdict(float)

    cache_hits: dict[str, float] = defaultdict(float)
    cache_misses: dict[str, float] = defaultdict(float)
    cache_invalidations: dict[str, float] = defaultdict(float)
    cache_op_sum: dict[str, float] = defaultdict(float)
    cache_op_count: dict[str, float] = defaultdict(float)

    db_op_sum: dict[str, float] = defaultdict(float)
    db_op_count: dict[str, float] = defaultdict(float)

    grafana_request_total: dict[str, float] = defaultdict(float)
    grafana_failure_total: dict[str, float] = defaultdict(float)
    grafana_latency_sum: dict[str, float] = defaultdict(float)
    grafana_latency_count: dict[str, float] = defaultdict(float)

    subscription_conflicts: dict[str, float] = defaultdict(float)
    share_link_expired: dict[str, float] = defaultdict(float)
    summary_source: dict[str, float] = defaultdict(float)

    for sample in samples:
        name = sample['name']
        labels = sample['labels']
        value = sample['value']

        if name == 'dashboard_hub_requests_total':
            path = labels.get('path', 'unknown')
            status = labels.get('status', 'unknown')
            request_total += value
            request_by_path_status[f'{path}|{status}'] += value
            request_by_status_family[f'{status[:1]}xx' if status and status[0].isdigit() else 'other'] += value
        elif name == 'dashboard_hub_request_latency_seconds_sum':
            request_latency_sum[labels.get('path', 'unknown')] += value
        elif name == 'dashboard_hub_request_latency_seconds_count':
            request_latency_count[labels.get('path', 'unknown')] += value
        elif name == 'dashboard_hub_requests_in_progress':
            inflight_by_path[labels.get('path', 'unknown')] += value
        elif name == 'dashboard_hub_request_exceptions_total':
            key = f"{labels.get('path', 'unknown')}|{labels.get('exception', 'unknown')}"
            exception_by_path[key] += value
        elif name == 'dashboard_hub_cache_hit_total':
            cache_hits[labels.get('cache_name', 'unknown')] += value
        elif name == 'dashboard_hub_cache_miss_total':
            cache_misses[labels.get('cache_name', 'unknown')] += value
        elif name == 'dashboard_hub_cache_invalidations_total':
            key = f"{labels.get('cache_name', 'unknown')}|{labels.get('reason', 'unknown')}"
            cache_invalidations[key] += value
        elif name == 'dashboard_hub_cache_operation_latency_seconds_sum':
            key = f"{labels.get('operation', 'unknown')}|{labels.get('cache_name', 'unknown')}"
            cache_op_sum[key] += value
        elif name == 'dashboard_hub_cache_operation_latency_seconds_count':
            key = f"{labels.get('operation', 'unknown')}|{labels.get('cache_name', 'unknown')}"
            cache_op_count[key] += value
        elif name == 'dashboard_hub_db_operation_latency_seconds_sum':
            db_op_sum[labels.get('operation', 'unknown')] += value
        elif name == 'dashboard_hub_db_operation_latency_seconds_count':
            db_op_count[labels.get('operation', 'unknown')] += value
        elif name == 'dashboard_hub_grafana_requests_total':
            key = f"{labels.get('endpoint', 'unknown')}|{labels.get('status', 'unknown')}"
            grafana_request_total[key] += value
        elif name == 'dashboard_hub_grafana_request_failures_total':
            key = f"{labels.get('endpoint', 'unknown')}|{labels.get('reason', 'unknown')}"
            grafana_failure_total[key] += value
        elif name == 'dashboard_hub_grafana_request_latency_seconds_sum':
            grafana_latency_sum[labels.get('endpoint', 'unknown')] += value
        elif name == 'dashboard_hub_grafana_request_latency_seconds_count':
            grafana_latency_count[labels.get('endpoint', 'unknown')] += value
        elif name == 'dashboard_hub_subscription_conflicts_total':
            subscription_conflicts[labels.get('channel', 'unknown')] += value
        elif name == 'dashboard_hub_share_link_expired_total':
            share_link_expired[labels.get('source', 'unknown')] += value
        elif name == 'dashboard_hub_summary_source_total':
            summary_source[labels.get('source', 'unknown')] += value

    http_latency_by_path: dict[str, Any] = {}
    for path, count in request_latency_count.items():
        total_sum = request_latency_sum.get(path, 0.0)
        http_latency_by_path[path] = {
            'count': int(count),
            'sum_ms': _round_ms(total_sum),
            'avg_ms': _round_ms(total_sum / count) if count else 0.0,
        }

    cache_ops: dict[str, Any] = {}
    for key, count in cache_op_count.items():
        total_sum = cache_op_sum.get(key, 0.0)
        operation, cache_name = key.split('|', 1)
        cache_ops[f'{operation}|{cache_name}'] = {
            'operation': operation,
            'cache_name': cache_name,
            'count': int(count),
            'sum_ms': _round_ms(total_sum),
            'avg_ms': _round_ms(total_sum / count) if count else 0.0,
        }

    db_ops: dict[str, Any] = {}
    for operation, count in db_op_count.items():
        total_sum = db_op_sum.get(operation, 0.0)
        db_ops[operation] = {
            'count': int(count),
            'sum_ms': _round_ms(total_sum),
            'avg_ms': _round_ms(total_sum / count) if count else 0.0,
        }

    grafana_ops: dict[str, Any] = {}
    for endpoint, count in grafana_latency_count.items():
        total_sum = grafana_latency_sum.get(endpoint, 0.0)
        grafana_ops[endpoint] = {
            'count': int(count),
            'sum_ms': _round_ms(total_sum),
            'avg_ms': _round_ms(total_sum / count) if count else 0.0,
        }

    return {
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'metrics_url': metrics_url,
        'http': {
            'total_requests': int(request_total),
            'requests_by_path_status': dict(sorted(request_by_path_status.items())),
            'requests_by_status_family': dict(sorted(request_by_status_family.items())),
            'latency_by_path': dict(sorted(http_latency_by_path.items())),
            'in_progress_by_path': {key: int(value) for key, value in sorted(inflight_by_path.items())},
            'exceptions_by_path': {key: int(value) for key, value in sorted(exception_by_path.items())},
        },
        'cache': {
            'hits_by_name': {key: int(value) for key, value in sorted(cache_hits.items())},
            'misses_by_name': {key: int(value) for key, value in sorted(cache_misses.items())},
            'invalidations_by_name_reason': {key: int(value) for key, value in sorted(cache_invalidations.items())},
            'operation_latency': dict(sorted(cache_ops.items())),
        },
        'database': {
            'operation_latency': dict(sorted(db_ops.items())),
        },
        'grafana_outbound': {
            'requests_by_endpoint_status': {key: int(value) for key, value in sorted(grafana_request_total.items())},
            'failures_by_endpoint_reason': {key: int(value) for key, value in sorted(grafana_failure_total.items())},
            'latency_by_endpoint': dict(sorted(grafana_ops.items())),
        },
        'business': {
            'subscription_conflicts_by_channel': {
                key: int(value) for key, value in sorted(subscription_conflicts.items())
            },
            'share_link_expired_by_source': {key: int(value) for key, value in sorted(share_link_expired.items())},
            'summary_source_by_type': {key: int(value) for key, value in sorted(summary_source.items())},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Collect structured Prometheus metric snapshot')
    parser.add_argument('--metrics-url', default='http://localhost:8000/metrics')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    payload = build_snapshot(args.metrics_url)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'metrics snapshot written to {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
