from __future__ import annotations

import os
from itertools import cycle

from locust import HttpUser, between, task


def _split_env(name: str) -> list[str]:
    raw = os.getenv(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


DASHBOARD_UIDS = _split_env('LOCUST_DASHBOARD_UIDS')
SHARE_TOKENS = _split_env('LOCUST_SHARE_TOKENS')
WARMUP_REQUESTS = max(1, int(os.getenv('LOCUST_WARMUP_REQUESTS', '3')))

_dashboard_cycle = cycle(DASHBOARD_UIDS) if DASHBOARD_UIDS else None
_share_cycle = cycle(SHARE_TOKENS) if SHARE_TOKENS else None


def _next_value(pool_cycle):
    if pool_cycle is None:
        return None
    return next(pool_cycle)


class HotReadUser(HttpUser):
    """热点读场景：以订阅列表为主，分享链接为辅。"""

    wait_time = between(0.5, 1.5)

    def on_start(self):
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

    @task(7)
    def read_subscriptions_hot(self):
        dashboard_uid = _next_value(_dashboard_cycle)
        if not dashboard_uid:
            return

        with self.client.get(
            f'/api/v1/dashboards/{dashboard_uid}/subscriptions',
            name='/api/v1/dashboards/{dashboard_uid}/subscriptions:hot_read',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}')

    @task(3)
    def read_share_link_hot(self):
        token = _next_value(_share_cycle)
        if not token:
            return

        with self.client.get(
            f'/api/v1/share-links/{token}',
            name='/api/v1/share-links/{token}:hot_read',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}')
