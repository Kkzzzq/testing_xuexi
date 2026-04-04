from __future__ import annotations

import os
from itertools import count, cycle
from typing import Iterable

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
ENABLE_SUMMARY_TASK = os.getenv('LOCUST_ENABLE_SUMMARY', '1').strip().lower() not in {'0', 'false', 'no'}

# 订阅与分享链路是默认主场景；摘要接口只作为补充验证。
SUBSCRIPTIONS_WEIGHT = 5
SHARE_LINK_WEIGHT = 5
CREATE_NORMAL_WEIGHT = 2
CREATE_CONFLICT_WEIGHT = 2
SUMMARY_WEIGHT = 1 if ENABLE_SUMMARY_TASK else 0

_CHANNELS = ('email', 'slack', 'webhook')
_login_counter = count(1)
_channel_counter = count(0)
_dashboard_cycle = cycle(DASHBOARD_UIDS) if DASHBOARD_UIDS else None
_share_cycle = cycle(SHARE_TOKENS) if SHARE_TOKENS else None


def _next_user_login() -> str:
    return f'locust_user_{next(_login_counter)}'


def _next_channel() -> str:
    return _CHANNELS[next(_channel_counter) % len(_CHANNELS)]


def _next_value(pool_cycle, values: Iterable[str]) -> str | None:
    if pool_cycle is None:
        return None
    return next(pool_cycle)


class DashboardHubUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        self._warm_up()

    def _warm_up(self):
        """预热只覆盖主链路：订阅列表与分享链接。"""
        for _ in range(WARMUP_REQUESTS):
            dashboard_uid = _next_value(_dashboard_cycle, DASHBOARD_UIDS)
            if dashboard_uid:
                self.client.get(
                    f'/api/v1/dashboards/{dashboard_uid}/subscriptions',
                    name='/warmup/subscriptions',
                )

            token = _next_value(_share_cycle, SHARE_TOKENS)
            if token:
                self.client.get(
                    f'/api/v1/share-links/{token}',
                    name='/warmup/share-link',
                )

    @task(SUBSCRIPTIONS_WEIGHT)
    def list_subscriptions(self):
        dashboard_uid = _next_value(_dashboard_cycle, DASHBOARD_UIDS)
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

    @task(SHARE_LINK_WEIGHT)
    def get_share_link(self):
        token = _next_value(_share_cycle, SHARE_TOKENS)
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

    @task(SUMMARY_WEIGHT)
    def get_dashboard_summary(self):
        """摘要接口保留，但只作为补充验证。"""
        if SUMMARY_WEIGHT == 0:
            return

        dashboard_uid = _next_value(_dashboard_cycle, DASHBOARD_UIDS)
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

    @task(CREATE_NORMAL_WEIGHT)
    def create_subscription_normal(self):
        dashboard_uid = _next_value(_dashboard_cycle, DASHBOARD_UIDS)
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
                response.failure(f'unexpected status={response.status_code}')

    @task(CREATE_CONFLICT_WEIGHT)
    def create_subscription_conflict(self):
        dashboard_uid = _next_value(_dashboard_cycle, DASHBOARD_UIDS)
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
