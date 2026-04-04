from __future__ import annotations

import os
from itertools import count

from locust import HttpUser, between, task


INVALID_SHARE_PREFIX = os.getenv('LOCUST_INVALID_SHARE_PREFIX', 'missing-token')
INVALID_DASHBOARD_PREFIX = os.getenv('LOCUST_INVALID_DASHBOARD_PREFIX', 'missing-dashboard')
_share_counter = count(1)
_dashboard_counter = count(1)


def _next_invalid_share_token() -> str:
    return f'{INVALID_SHARE_PREFIX}-{next(_share_counter)}'


def _next_invalid_dashboard_uid() -> str:
    return f'{INVALID_DASHBOARD_PREFIX}-{next(_dashboard_counter)}'


class CachePenetrationUser(HttpUser):
    """缓存穿透专项：持续请求不存在的数据，观察回源与稳定性。"""

    wait_time = between(0.3, 1.0)

    @task(6)
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
                response.failure(f'unexpected status={response.status_code}')

    @task(4)
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
                response.failure(f'unexpected status={response.status_code}')
