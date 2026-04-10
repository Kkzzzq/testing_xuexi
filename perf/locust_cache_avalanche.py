from __future__ import annotations

import os
from itertools import cycle
from urllib.parse import urljoin

import gevent
import gevent.lock
import redis
import requests
from locust import HttpUser, between, task


def _split_env(name: str) -> list[str]:
    raw = os.getenv(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, '') else default


DASHBOARD_UIDS = _split_env('LOCUST_DASHBOARD_UIDS')
SHARE_TOKENS = _split_env('LOCUST_SHARE_TOKENS')
HOTSET_SIZE = max(1, int(os.getenv('LOCUST_AVALANCHE_HOTSET_SIZE', '6')))
WAVE_INTERVAL_SECONDS = _env_float('LOCUST_AVALANCHE_WAVE_INTERVAL_SECONDS', 12.0)
WARMUP_TIMEOUT_SECONDS = _env_float('LOCUST_WARMUP_TIMEOUT_SECONDS', 5.0)
WAIT_MIN_SECONDS = _env_float('LOCUST_WAIT_MIN_SECONDS', 0.0)
WAIT_MAX_SECONDS = _env_float('LOCUST_WAIT_MAX_SECONDS', 0.02)
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD') or None

HOT_DASHBOARD_UIDS = DASHBOARD_UIDS[:HOTSET_SIZE]
HOT_SHARE_TOKENS = SHARE_TOKENS[:HOTSET_SIZE]
_dashboard_cycle = cycle(HOT_DASHBOARD_UIDS) if HOT_DASHBOARD_UIDS else None
_share_cycle = cycle(HOT_SHARE_TOKENS) if HOT_SHARE_TOKENS else None
_setup_lock = gevent.lock.Semaphore()
_setup_done = False
_wave_started = False


def _base_url(user: HttpUser) -> str:
    host = getattr(user.environment, 'host', None) or getattr(user, 'host', None) or ''
    return host.rstrip('/') + '/'


def _next_value(pool_cycle):
    if pool_cycle is None:
        return None
    return next(pool_cycle)


def _build_redis_client() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
    )


def _subscriptions_cache_key(dashboard_uid: str) -> str:
    return f'dashhub:subscriptions:{dashboard_uid}'


def _dashboard_exists_cache_key(dashboard_uid: str) -> str:
    return f'dashhub:dashboard_exists:{dashboard_uid}'


def _share_cache_key(token: str) -> str:
    return f'dashhub:share:{token}'


def _warmup_all_hot_keys(user: HttpUser) -> None:
    base_url = _base_url(user)
    for dashboard_uid in HOT_DASHBOARD_UIDS:
        response = requests.get(
            urljoin(base_url, f'/api/v1/dashboards/{dashboard_uid}/subscriptions'),
            timeout=WARMUP_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f'failed to warm subscriptions cache for {dashboard_uid}, status={response.status_code}'
            )
    for token in HOT_SHARE_TOKENS:
        response = requests.get(
            urljoin(base_url, f'/api/v1/share-links/{token}'),
            timeout=WARMUP_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f'failed to warm share-link cache for {token}, status={response.status_code}'
            )


def _invalidate_wave_forever() -> None:
    redis_client = _build_redis_client()
    while True:
        gevent.sleep(max(1.0, WAVE_INTERVAL_SECONDS))
        keys: list[str] = []
        for dashboard_uid in HOT_DASHBOARD_UIDS:
            keys.append(_dashboard_exists_cache_key(dashboard_uid))
            keys.append(_subscriptions_cache_key(dashboard_uid))
        for token in HOT_SHARE_TOKENS:
            keys.append(_share_cache_key(token))
        if keys:
            redis_client.delete(*keys)


def _prepare_avalanche(user: HttpUser) -> None:
    global _setup_done, _wave_started
    if not HOT_DASHBOARD_UIDS and not HOT_SHARE_TOKENS:
        return

    with _setup_lock:
        if not _setup_done:
            _warmup_all_hot_keys(user)
            _setup_done = True
        if not _wave_started:
            gevent.spawn(_invalidate_wave_forever)
            _wave_started = True


class CacheAvalancheUser(HttpUser):
    """缓存雪崩专项：预热多组热点 key，再按波次批量删 key，模拟同批热点同时过期。"""

    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    def on_start(self):
        _prepare_avalanche(self)

    @task(7)
    def read_subscriptions_hotset(self):
        dashboard_uid = _next_value(_dashboard_cycle)
        if not dashboard_uid:
            return

        with self.client.get(
            f'/api/v1/dashboards/{dashboard_uid}/subscriptions',
            name='/api/v1/dashboards/{dashboard_uid}/subscriptions:avalanche',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}, body={response.text[:200]}')

    @task(3)
    def read_share_links_hotset(self):
        token = _next_value(_share_cycle)
        if not token:
            return

        with self.client.get(
            f'/api/v1/share-links/{token}',
            name='/api/v1/share-links/{token}:avalanche',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}, body={response.text[:200]}')
