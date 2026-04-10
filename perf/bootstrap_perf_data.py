from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def _basic_auth_header(username: str, password: str) -> str:
    import base64

    token = base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('ascii')
    return f'Basic {token}'


def _request_json(
    url: str,
    method: str = 'GET',
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(
            f'HTTP {exc.code} calling {method} {url}: {body[:400]}'
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'Failed to call {method} {url}: {exc.reason}') from exc




def _is_retryable_error(message: str, retryable_status_codes: set[int] | None = None) -> bool:
    if 'Failed to call' in message:
        return True
    statuses = retryable_status_codes or {404, 409, 429, 500, 502, 503, 504}
    return any(f'HTTP {status} ' in message for status in statuses)


def _request_json_with_retry(
    url: str,
    method: str = 'GET',
    headers: dict[str, str] | None = None,
    payload: dict | None = None,
    *,
    attempts: int = 5,
    initial_sleep_seconds: float = 0.5,
    retryable_status_codes: set[int] | None = None,
):
    last_error: RuntimeError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _request_json(url, method=method, headers=headers, payload=payload)
        except RuntimeError as exc:
            last_error = exc
            if attempt >= attempts or not _is_retryable_error(str(exc), retryable_status_codes):
                raise
            time.sleep(initial_sleep_seconds * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f'failed to call {method} {url}')


def _wait_until_dashboard_readable(grafana_base_url: str, dashboard_uid: str, auth_header: str) -> None:
    _request_json_with_retry(
        f'{grafana_base_url}/api/dashboards/uid/{dashboard_uid}',
        method='GET',
        headers={'Authorization': auth_header},
        attempts=8,
        initial_sleep_seconds=0.5,
        retryable_status_codes={404, 500, 502, 503, 504},
    )

def create_perf_seed_data(
    grafana_base_url: str,
    dashboard_hub_base_url: str,
    dashboard_count: int,
    subscriptions_per_dashboard: int,
    admin_user: str,
    admin_password: str,
    run_suffix: str,
    conflict_user_login: str,
):
    dashboard_uids: list[str] = []
    share_tokens: list[str] = []

    auth_header = _basic_auth_header(admin_user, admin_password)

    for index in range(1, dashboard_count + 1):
        dashboard_payload = {
            'dashboard': {
                'id': None,
                'uid': f'locust-dashboard-{run_suffix}-{index}',
                'title': f'Locust Dashboard {run_suffix}-{index}',
                'timezone': 'browser',
                'schemaVersion': 39,
                'version': 0,
                'panels': [
                    {
                        'id': 1,
                        'type': 'timeseries',
                        'title': f'HTTP Latency {index}',
                        'datasource': {'type': 'testdata', 'uid': 'grafana'},
                        'gridPos': {'h': 8, 'w': 12, 'x': 0, 'y': 0},
                    },
                    {
                        'id': 2,
                        'type': 'stat',
                        'title': f'Error Rate {index}',
                        'datasource': {'type': 'testdata', 'uid': 'grafana'},
                        'gridPos': {'h': 8, 'w': 12, 'x': 12, 'y': 0},
                    },
                ],
            },
            'overwrite': True,
        }
        dashboard_result = _request_json_with_retry(
            f'{grafana_base_url}/api/dashboards/db',
            method='POST',
            headers={
                'Content-Type': 'application/json',
                'Authorization': auth_header,
            },
            payload=dashboard_payload,
        )
        dashboard_uid = dashboard_result['uid']
        dashboard_uids.append(dashboard_uid)
        _wait_until_dashboard_readable(grafana_base_url, dashboard_uid, auth_header)

        for subscription_index in range(1, subscriptions_per_dashboard + 1):
            _request_json_with_retry(
                f'{dashboard_hub_base_url}/api/v1/subscriptions',
                method='POST',
                headers={'Content-Type': 'application/json'},
                payload={
                    'dashboard_uid': dashboard_uid,
                    'user_login': f'perf_seed_user_{run_suffix}_{index}_{subscription_index}',
                    'channel': 'email',
                    'cron': '0 */6 * * *',
                },
            )

        expire_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        share_result = _request_json_with_retry(
            f'{dashboard_hub_base_url}/api/v1/share-links',
            method='POST',
            headers={'Content-Type': 'application/json'},
            payload={'dashboard_uid': dashboard_uid, 'expire_at': expire_at},
        )
        share_tokens.append(share_result['token'])

    if not dashboard_uids or not share_tokens:
        raise RuntimeError('performance seed data generation did not produce dashboards/share links')

    hot_dashboard_uid = dashboard_uids[0]
    hot_share_token = share_tokens[0]

    # 预先种入一条固定冲突数据，让写冲突场景从启动开始就能稳定打出 409。
    _request_json_with_retry(
        f'{dashboard_hub_base_url}/api/v1/subscriptions',
        method='POST',
        headers={'Content-Type': 'application/json'},
        payload={
            'dashboard_uid': hot_dashboard_uid,
            'user_login': conflict_user_login,
            'channel': 'email',
            'cron': '0 */6 * * *',
        },
        retryable_status_codes={500, 502, 503, 504},
    )

    return dashboard_uids, share_tokens, hot_dashboard_uid, hot_share_token


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Bootstrap dashboards, subscriptions and share links for performance scenarios'
    )
    parser.add_argument('--grafana-base-url', default=os.getenv('GRAFANA_BASE_URL', 'http://localhost:3000'))
    parser.add_argument('--dashboard-hub-base-url', default=os.getenv('DASHBOARD_HUB_BASE_URL', 'http://localhost:8000'))
    parser.add_argument('--dashboard-count', type=int, default=int(os.getenv('LOCUST_DASHBOARD_COUNT', '5')))
    parser.add_argument(
        '--subscriptions-per-dashboard',
        type=int,
        default=int(os.getenv('LOCUST_SUBSCRIPTIONS_PER_DASHBOARD', '3')),
    )
    parser.add_argument('--admin-user', default=os.getenv('GRAFANA_ADMIN_USER', 'admin'))
    parser.add_argument('--admin-password', default=os.getenv('GRAFANA_ADMIN_PASSWORD', 'admin'))
    parser.add_argument('--github-env', default=os.getenv('GITHUB_ENV'))
    args = parser.parse_args()

    run_suffix = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S') + '-' + uuid4().hex[:6]
    conflict_user_login = f'locust_conflict_user_{run_suffix}'

    dashboard_uids, share_tokens, hot_dashboard_uid, hot_share_token = create_perf_seed_data(
        grafana_base_url=args.grafana_base_url,
        dashboard_hub_base_url=args.dashboard_hub_base_url,
        dashboard_count=args.dashboard_count,
        subscriptions_per_dashboard=args.subscriptions_per_dashboard,
        admin_user=args.admin_user,
        admin_password=args.admin_password,
        run_suffix=run_suffix,
        conflict_user_login=conflict_user_login,
    )

    result = {
        'LOCUST_RUN_SUFFIX': run_suffix,
        'LOCUST_DASHBOARD_UIDS': ','.join(dashboard_uids),
        'LOCUST_SHARE_TOKENS': ','.join(share_tokens),
        'LOCUST_HOT_DASHBOARD_UID': hot_dashboard_uid,
        'LOCUST_HOT_SHARE_TOKEN': hot_share_token,
        'LOCUST_CONFLICT_DASHBOARD_UID': hot_dashboard_uid,
        'LOCUST_CONFLICT_USER_LOGIN': conflict_user_login,
    }

    if args.github_env:
        with open(args.github_env, 'a', encoding='utf-8') as fh:
            for key, value in result.items():
                fh.write(f'{key}={value}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
