from __future__ import annotations

import argparse
import csv
from pathlib import Path


PROFILES = {
    'hot_read': {
        '/api/v1/dashboards/{dashboard_uid}/subscriptions:hot_read': {
            'max_p95_ms': 800,
            'max_p99_ms': 1200,
            'max_failures': 0,
        },
        '/api/v1/share-links/{token}:hot_read': {
            'max_p95_ms': 900,
            'max_p99_ms': 1300,
            'max_failures': 0,
        },
        'Aggregated': {'max_error_rate': 0.01, 'min_request_count': 1000, 'min_rps': 5.0},
    },
    'write_conflict': {
        '/api/v1/subscriptions:create_normal': {
            'max_p95_ms': 1200,
            'max_p99_ms': 1800,
            'max_failures': 0,
        },
        '/api/v1/subscriptions:create_conflict': {
            'max_p95_ms': 1200,
            'max_p99_ms': 1800,
            'max_failures': 0,
        },
        'Aggregated': {'max_error_rate': 0.01, 'min_request_count': 500, 'min_rps': 2.0},
    },
    'cache_penetration': {
        '/api/v1/share-links/{token}:penetration': {
            'max_p95_ms': 900,
            'max_p99_ms': 1300,
            'max_failures': 0,
        },
        '/api/v1/dashboards/{dashboard_uid}/subscriptions:penetration': {
            'max_p95_ms': 1100,
            'max_p99_ms': 1600,
            'max_failures': 0,
        },
        'Aggregated': {'max_error_rate': 0.01, 'min_request_count': 800, 'min_rps': 4.0},
    },
    'cache_breakdown': {
        '/api/v1/dashboards/{dashboard_uid}/subscriptions:breakdown': {
            'max_p95_ms': 1300,
            'max_p99_ms': 1900,
            'max_failures': 0,
        },
        'Aggregated': {'max_error_rate': 0.01, 'min_request_count': 800, 'min_rps': 4.0},
    },
    'cache_avalanche': {
        '/api/v1/dashboards/{dashboard_uid}/subscriptions:avalanche': {
            'max_p95_ms': 1600,
            'max_p99_ms': 2300,
            'max_failures': 0,
        },
        '/api/v1/share-links/{token}:avalanche': {
            'max_p95_ms': 1600,
            'max_p99_ms': 2300,
            'max_failures': 0,
        },
        'Aggregated': {'max_error_rate': 0.02, 'min_request_count': 1000, 'min_rps': 4.0},
    },
}


def _to_float(value: str | None, default: float = 0.0) -> float:
    if value in (None, '', 'N/A', 'n/a', 'nan', 'NaN'):
        return default
    return float(value)


def _to_int(value: str | None, default: int = 0) -> int:
    if value in (None, '', 'N/A', 'n/a', 'nan', 'NaN'):
        return default
    return int(float(value))


def load_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with csv_path.open('r', encoding='utf-8', newline='') as fh:
        for row in csv.DictReader(fh):
            name = row.get('Name') or row.get('Type')
            if not name:
                continue
            rows[name] = row
    return rows


def assert_thresholds(rows: dict[str, dict[str, str]], profile: str):
    rules = PROFILES[profile]
    errors: list[str] = []

    for name, rule in rules.items():
        row = rows.get(name)
        if row is None:
            errors.append(f'missing row for {name}')
            continue

        if 'max_p95_ms' in rule:
            raw_p95 = row.get('95%')
            if raw_p95 in (None, '', 'N/A', 'n/a'):
                errors.append(f'missing or invalid p95 value for {name}')
            else:
                p95 = _to_float(raw_p95)
                if p95 > rule['max_p95_ms']:
                    errors.append(f'{name} p95={p95}ms > {rule["max_p95_ms"]}ms')

        if 'max_p99_ms' in rule:
            raw_p99 = row.get('99%')
            if raw_p99 in (None, '', 'N/A', 'n/a'):
                errors.append(f'missing or invalid p99 value for {name}')
            else:
                p99 = _to_float(raw_p99)
                if p99 > rule['max_p99_ms']:
                    errors.append(f'{name} p99={p99}ms > {rule["max_p99_ms"]}ms')

        if 'max_failures' in rule:
            failures = _to_int(row.get('Failure Count'))
            if failures > rule['max_failures']:
                errors.append(f'{name} failures={failures} > {rule["max_failures"]}')

        request_count = _to_int(row.get('Request Count'))

        if 'max_error_rate' in rule:
            failures = _to_int(row.get('Failure Count'))
            if request_count <= 0:
                errors.append(f'{name} request_count is missing or zero')
            else:
                error_rate = failures / request_count
                if error_rate > rule['max_error_rate']:
                    errors.append(
                        f'{name} error_rate={error_rate:.4f} > {rule["max_error_rate"]:.4f}'
                    )

        if 'min_request_count' in rule and request_count < rule['min_request_count']:
            errors.append(f'{name} request_count={request_count} < {rule["min_request_count"]}')

        if 'min_rps' in rule:
            rps = _to_float(row.get('Requests/s'))
            if rps < rule['min_rps']:
                errors.append(f'{name} requests/s={rps:.2f} < {rule["min_rps"]:.2f}')

    if errors:
        raise SystemExit('Performance thresholds failed\n- ' + '\n- '.join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description='Assert Locust CSV performance thresholds')
    parser.add_argument('--csv', default='perf-results/locust_stats.csv')
    parser.add_argument('--profile', choices=sorted(PROFILES), required=True)
    args = parser.parse_args()

    rows = load_rows(Path(args.csv))
    assert_thresholds(rows, args.profile)
    print(f'Performance thresholds passed for profile={args.profile}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
