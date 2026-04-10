from __future__ import annotations

import os
from urllib.parse import urljoin

import gevent
import gevent.lock
import redis
import requests
from locust import HttpUser, between, task


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, '') else default


HOT_DASHBOARD_UID = os.getenv('LOCUST_HOT_DASHBOARD_UID', '').strip()
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD') or None
WARMUP_REQUESTS = max(1, int(os.getenv('LOCUST_BREAKDOWN_WARMUP_REQUESTS', '2')))
WARMUP_TIMEOUT_SECONDS = _env_float('LOCUST_WARMUP_TIMEOUT_SECONDS', 5.0)
INVALIDATE_INTERVAL_SECONDS = _env_float('LOCUST_BREAKDOWN_INVALIDATE_INTERVAL_SECONDS', 2.5)
WAIT_MIN_SECONDS = _env_float('LOCUST_WAIT_MIN_SECONDS', 0.0)
WAIT_MAX_SECONDS = _env_float('LOCUST_WAIT_MAX_SECONDS', 0.01)

_setup_lock = gevent.lock.Semaphore()
_setup_done = False
_invalidator_started = False


def _subscriptions_cache_key(dashboard_uid: str) -> str:
    return f'dashhub:subscriptions:{dashboard_uid}'


def _base_url(user: HttpUser) -> str:
    host = getattr(user.environment, 'host', None) or getattr(user, 'host', None) or ''
    return host.rstrip('/') + '/'


def _build_redis_client() -> redis.Redis:
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
    )


def _warmup_subscriptions_cache(user: HttpUser) -> None:
    for _ in range(WARMUP_REQUESTS):
        response = requests.get(
            urljoin(_base_url(user), f'/api/v1/dashboards/{HOT_DASHBOARD_UID}/subscriptions'),
            timeout=WARMUP_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f'failed to warm subscriptions cache for {HOT_DASHBOARD_UID}, '
                f'status={response.status_code}'
            )


def _invalidate_hot_key_forever() -> None:
    redis_client = _build_redis_client()
    cache_key = _subscriptions_cache_key(HOT_DASHBOARD_UID)
    while True:
        gevent.sleep(max(0.2, INVALIDATE_INTERVAL_SECONDS))
        redis_client.delete(cache_key)


def _prepare_breakdown_loop(user: HttpUser) -> None:
    global _setup_done, _invalidator_started
    if not HOT_DASHBOARD_UID:
        return

    with _setup_lock:
        if not _setup_done:
            _warmup_subscriptions_cache(user)
            _setup_done = True
        if not _invalidator_started:
            gevent.spawn(_invalidate_hot_key_forever)
            _invalidator_started = True


class CacheBreakdownUser(HttpUser):
    """缓存击穿专项：单热点 key 预热后按固定间隔反复删 key，持续制造回源与回填。"""

    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    def on_start(self):
        _prepare_breakdown_loop(self)

    @task
    def hit_broken_hot_key(self):
        if not HOT_DASHBOARD_UID:
            return

        with self.client.get(
            f'/api/v1/dashboards/{HOT_DASHBOARD_UID}/subscriptions',
            name='/api/v1/dashboards/{dashboard_uid}/subscriptions:breakdown',
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f'unexpected status={response.status_code}, body={response.text[:200]}')
