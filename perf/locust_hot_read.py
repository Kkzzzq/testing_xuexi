from __future__ import annotations

import os
from itertools import cycle
from urllib.parse import urljoin

import requests
from gevent.lock import Semaphore
from locust import HttpUser, between, task


def _split_env(name: str) -> list[str]:
    raw = os.getenv(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, '') else default


DASHBOARD_UIDS = _split_env('LOCUST_DASHBOARD_UIDS')
SHARE_TOKENS = _split_env('LOCUST_SHARE_TOKENS')
WARMUP_REQUESTS = max(1, int(os.getenv('LOCUST_WARMUP_REQUESTS', '2')))
WARMUP_TIMEOUT_SECONDS = _env_float('LOCUST_WARMUP_TIMEOUT_SECONDS', 5.0)
WAIT_MIN_SECONDS = _env_float('LOCUST_WAIT_MIN_SECONDS', 0.01)
WAIT_MAX_SECONDS = _env_float('LOCUST_WAIT_MAX_SECONDS', 0.05)

_dashboard_cycle = cycle(DASHBOARD_UIDS) if DASHBOARD_UIDS else None
_share_cycle = cycle(SHARE_TOKENS) if SHARE_TOKENS else None
_warmup_lock = Semaphore()
_warmup_done = False


def _next_value(pool_cycle):
    if pool_cycle is None:
        return None
    return next(pool_cycle)


def _base_url(user: HttpUser) -> str:
    host = getattr(user.environment, 'host', None) or getattr(user, 'host', None) or ''
    return host.rstrip('/') + '/'


def _warmup_get(user: HttpUser, path: str) -> None:
    response = requests.get(urljoin(_base_url(user), path.lstrip('/')), timeout=WARMUP_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise RuntimeError(f'warmup request failed for {path}: status={response.status_code}, body={response.text[:200]}')


class HotReadUser(HttpUser):
    """热点读场景：高比例读取，默认按更激进的等待时间压测。"""

    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    def on_start(self):
        global _warmup_done

        if _warmup_done:
            return

        with _warmup_lock:
            if _warmup_done:
                return

            for _ in range(WARMUP_REQUESTS):
                dashboard_uid = _next_value(_dashboard_cycle)
                if dashboard_uid:
                    _warmup_get(self, f'/api/v1/dashboards/{dashboard_uid}/subscriptions')
                token = _next_value(_share_cycle)
                if token:
                    _warmup_get(self, f'/api/v1/share-links/{token}')

            _warmup_done = True

    @task(8)
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
                response.failure(f'unexpected status={response.status_code}, body={response.text[:200]}')

    @task(2)
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
                response.failure(f'unexpected status={response.status_code}, body={response.text[:200]}')
