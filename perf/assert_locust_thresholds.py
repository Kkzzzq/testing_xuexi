from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_RULES = {
    '/api/v1/dashboards/{dashboard_uid}/subscriptions': {
        'max_p95_ms': 800,
        'max_failures': 0,
        'required': True,
    },
    '/api/v1/share-links/{token}': {
        'max_p95_ms': 800,
        'max_failures': 0,
        'required': True,
    },
    '/api/v1/subscriptions:create_normal': {
        'max_p95_ms': 1200,
        'max_failures': 0,
        'required': True,
    },
    '/api/v1/subscriptions:create_conflict': {
        'max_p95_ms': 1200,
        'max_failures': 0,
        'required': True,
    },
    '/api/v1/dashboards/{dashboard_uid}/summary': {
        'max_p95_ms': 2500,
        'max_failures': 0,
        'required': False,
    },
    'Aggregated': {'max_error_rate': 0.01, 'required': True},
}


def _to_float(value: str | None, default: float = 0.0) -> float:
    if value in (None, ''):
        return default
    return float(value)


def _to_int(value: str | None, default: int = 0) -> int:
    if value in (None, ''):
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


def assert_thresholds(rows: dict[str, dict[str, str]]):
    errors: list[str] = []

    for name, rule in DEFAULT_RULES.items():
        row = rows.get(name)
        if row is None:
            if rule.get('required', True):
                errors.append(f'missing row for {name}')
            continue

        if 'max_p95_ms' in rule:
            p95 = _to_float(row.get('95%'))
            if p95 > rule['max_p95_ms']:
                errors.append(f'{name} p95={p95}ms > {rule["max_p95_ms"]}ms')

        if 'max_failures' in rule:
            failures = _to_int(row.get('Failure Count'))
            if failures > rule['max_failures']:
                errors.append(f'{name} failures={failures} > {rule["max_failures"]}')

        if 'max_error_rate' in rule:
            request_count = _to_int(row.get('Request Count'))
            failures = _to_int(row.get('Failure Count'))
            error_rate = failures / request_count if request_count else 1.0
            if error_rate > rule['max_error_rate']:
                errors.append(f'{name} error_rate={error_rate:.4f} > {rule["max_error_rate"]:.4f}')

    if errors:
        raise SystemExit('Performance thresholds failed:\n- ' + '\n- '.join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description='Assert Locust CSV performance thresholds')
    parser.add_argument('--csv', default='perf-results/locust_stats.csv')
    args = parser.parse_args()

    rows = load_rows(Path(args.csv))
    assert_thresholds(rows)
    print('Performance thresholds passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
