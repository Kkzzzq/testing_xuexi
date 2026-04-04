from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone


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
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


def create_perf_seed_data(
    grafana_base_url: str,
    dashboard_hub_base_url: str,
    dashboard_count: int,
    subscriptions_per_dashboard: int,
    admin_user: str,
    admin_password: str,
):
    dashboard_uids: list[str] = []
    share_tokens: list[str] = []

    auth_header = _basic_auth_header(admin_user, admin_password)

    for index in range(1, dashboard_count + 1):
        dashboard_payload = {
            'dashboard': {
                'id': None,
                'uid': f'locust-dashboard-{index}',
                'title': f'Locust Dashboard {index}',
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
        dashboard_result = _request_json(
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

        for subscription_index in range(1, subscriptions_per_dashboard + 1):
            _request_json(
                f'{dashboard_hub_base_url}/api/v1/subscriptions',
                method='POST',
                headers={'Content-Type': 'application/json'},
                payload={
                    'dashboard_uid': dashboard_uid,
                    'user_login': f'perf_seed_user_{index}_{subscription_index}',
                    'channel': 'email',
                    'cron': '0 */6 * * *',
                },
            )

        expire_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        share_result = _request_json(
            f'{dashboard_hub_base_url}/api/v1/share-links',
            method='POST',
            headers={'Content-Type': 'application/json'},
            payload={'dashboard_uid': dashboard_uid, 'expire_at': expire_at},
        )
        share_tokens.append(share_result['token'])

    hot_dashboard_uid = dashboard_uids[0] if dashboard_uids else ''
    hot_share_token = share_tokens[0] if share_tokens else ''
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

    dashboard_uids, share_tokens, hot_dashboard_uid, hot_share_token = create_perf_seed_data(
        grafana_base_url=args.grafana_base_url,
        dashboard_hub_base_url=args.dashboard_hub_base_url,
        dashboard_count=args.dashboard_count,
        subscriptions_per_dashboard=args.subscriptions_per_dashboard,
        admin_user=args.admin_user,
        admin_password=args.admin_password,
    )

    result = {
        'LOCUST_DASHBOARD_UIDS': ','.join(dashboard_uids),
        'LOCUST_SHARE_TOKENS': ','.join(share_tokens),
        'LOCUST_HOT_DASHBOARD_UID': hot_dashboard_uid,
        'LOCUST_HOT_SHARE_TOKEN': hot_share_token,
        'LOCUST_CONFLICT_USER_LOGIN': 'locust_conflict_user',
    }

    if args.github_env:
        with open(args.github_env, 'a', encoding='utf-8') as fh:
            for key, value in result.items():
                fh.write(f'{key}={value}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
