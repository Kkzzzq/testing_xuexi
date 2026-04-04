from __future__ import annotations

import os
from itertools import count, cycle

from locust import HttpUser, between, task


def _split_env(name: str) -> list[str]:
    raw = os.getenv(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


def _resolve_dashboard_uids() -> list[str]:
    values = _split_env('LOCUST_DASHBOARD_UIDS')
    if values:
        return values
    fallback = os.getenv('LOCUST_DASHBOARD_UID', 'replace-me').strip()
    return [] if fallback == 'replace-me' else [fallback]


def _resolve_share_tokens() -> list[str]:
    values = _split_env('LOCUST_SHARE_TOKENS')
    if values:
        return values
    fallback = os.getenv('LOCUST_SHARE_TOKEN', 'replace-me').strip()
    return [] if fallback == 'replace-me' else [fallback]


DASHBOARD_UIDS = _resolve_dashboard_uids()
SHARE_TOKENS = _resolve_share_tokens()
CONFLICT_USER_LOGIN = os.getenv('LOCUST_CONFLICT_USER_LOGIN', 'locust_conflict_user')
WARMUP_REQUESTS = max(1, int(os.getenv('LOCUST_WARMUP_REQUESTS', '2')))
ENABLE_SUMMARY = os.getenv('LOCUST_ENABLE_SUMMARY', 'true').strip().lower() not in {'0', 'false', 'no'}

_CHANNELS = ('email', 'slack', 'webhook')
_login_counter = count(1)
_channel_counter = count(0)
_dashboard_cycle = cycle(DASHBOARD_UIDS) if DASHBOARD_UIDS else None
_share_cycle = cycle(SHARE_TOKENS) if SHARE_TOKENS else None


def _next_user_login() -> str:
    return f'locust_user_{next(_login_counter)}'


def _next_channel() -> str:
    return _CHANNELS[next(_channel_counter) % len(_CHANNELS)]


def _next_value(pool_cycle) -> str | None:
    if pool_cycle is None:
        return None
    return next(pool_cycle)


class DashboardHubUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        self._warm_up()

    def _warm_up(self):
        for _ in range(WARMUP_REQUESTS):
            dashboard_uid = _next_value(_dashboard_cycle)
            if dashboard_uid:
                self.client.get(
                    f'/api/v1/dashboards/{dashboard_uid}/subscriptions',
                    name='/warmup/subscriptions',
                )

            token = _next_value(_share_cycle)
            if token:
                self.client.get(
                    f'/api/v1/share-links/{token}',
                    name='/warmup/share-link',
                )

    @task(5)
    def list_subscriptions(self):
        dashboard_uid = _next_value(_dashboard_cycle)
        if not dashboard_uid:
            return

        with self.client.get(
            f'/api/v1/dashboards/{dashboard_uid}/subscriptions',
            name='/api/v1/dashboards/{dashboard_uid}/subscriptions',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}')

    @task(5)
    def get_share_link(self):
        token = _next_value(_share_cycle)
        if not token:
            return

        with self.client.get(
            f'/api/v1/share-links/{token}',
            name='/api/v1/share-links/{token}',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}')

    @task(1)
    def get_dashboard_summary(self):
        if not ENABLE_SUMMARY:
            return

        dashboard_uid = _next_value(_dashboard_cycle)
        if not dashboard_uid:
            return

        with self.client.get(
            f'/api/v1/dashboards/{dashboard_uid}/summary',
            name='/api/v1/dashboards/{dashboard_uid}/summary',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}')

    @task(2)
    def create_subscription_normal(self):
        dashboard_uid = _next_value(_dashboard_cycle)
        if not dashboard_uid:
            return

        payload = {
            'dashboard_uid': dashboard_uid,
            'user_login': _next_user_login(),
            'channel': _next_channel(),
            'cron': '0 */6 * * *',
        }

        with self.client.post(
            '/api/v1/subscriptions',
            json=payload,
            name='/api/v1/subscriptions:create_normal',
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}, body={response.text[:200]}')

    @task(2)
    def create_subscription_conflict(self):
        dashboard_uid = _next_value(_dashboard_cycle)
        if not dashboard_uid:
            return

        payload = {
            'dashboard_uid': dashboard_uid,
            'user_login': CONFLICT_USER_LOGIN,
            'channel': 'email',
            'cron': '0 */6 * * *',
        }

        with self.client.post(
            '/api/v1/subscriptions',
            json=payload,
            name='/api/v1/subscriptions:create_conflict',
            catch_response=True,
        ) as response:
            if response.status_code in (201, 409):
                response.success()
            else:
                response.failure(
                    f'unexpected status={response.status_code}, body={response.text[:200]}'
                )
