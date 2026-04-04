from __future__ import annotations

import os
from itertools import count

from locust import HttpUser, between, task


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, '') else default


INVALID_SHARE_PREFIX = os.getenv('LOCUST_INVALID_SHARE_PREFIX', 'missing-token')
INVALID_DASHBOARD_PREFIX = os.getenv('LOCUST_INVALID_DASHBOARD_PREFIX', 'missing-dashboard')
WAIT_MIN_SECONDS = _env_float('LOCUST_WAIT_MIN_SECONDS', 0.0)
WAIT_MAX_SECONDS = _env_float('LOCUST_WAIT_MAX_SECONDS', 0.03)
_share_counter = count(1)
_dashboard_counter = count(1)


def _next_invalid_share_token() -> str:
    return f'{INVALID_SHARE_PREFIX}-{next(_share_counter)}'


def _next_invalid_dashboard_uid() -> str:
    return f'{INVALID_DASHBOARD_PREFIX}-{next(_dashboard_counter)}'


class CachePenetrationUser(HttpUser):
    """缓存穿透专项：持续放大不存在数据请求，逼近下游回源瓶颈。"""

    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    @task(7)
    def invalid_share_link_penetration(self):
        token = _next_invalid_share_token()
        with self.client.get(
            f'/api/v1/share-links/{token}',
            name='/api/v1/share-links/{token}:penetration',
            catch_response=True,
        ) as response:
            if response.status_code == 404:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}, body={response.text[:200]}')

    @task(3)
    def invalid_dashboard_subscriptions_penetration(self):
        dashboard_uid = _next_invalid_dashboard_uid()
        with self.client.get(
            f'/api/v1/dashboards/{dashboard_uid}/subscriptions',
            name='/api/v1/dashboards/{dashboard_uid}/subscriptions:penetration',
            catch_response=True,
        ) as response:
            if response.status_code == 404:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}, body={response.text[:200]}')
