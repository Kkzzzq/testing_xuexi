from __future__ import annotations

import os

import gevent.lock
import redis
from locust import HttpUser, between, task


HOT_DASHBOARD_UID = os.getenv('LOCUST_HOT_DASHBOARD_UID', '').strip()
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD') or None
WARMUP_REQUESTS = max(1, int(os.getenv('LOCUST_BREAKDOWN_WARMUP_REQUESTS', '2')))

_setup_lock = gevent.lock.Semaphore()
_setup_done = False


def _subscriptions_cache_key(dashboard_uid: str) -> str:
    return f'dashhub:subscriptions:{dashboard_uid}'


def _prepare_hot_key(client) -> None:
    global _setup_done
    if _setup_done or not HOT_DASHBOARD_UID:
        return

    with _setup_lock:
        if _setup_done:
            return

        for _ in range(WARMUP_REQUESTS):
            response = client.get(
                f'/api/v1/dashboards/{HOT_DASHBOARD_UID}/subscriptions',
                name='/setup/subscriptions:warm_cache',
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f'failed to warm subscriptions cache for {HOT_DASHBOARD_UID}, '
                    f'status={response.status_code}'
                )

        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
        )
        redis_client.delete(_subscriptions_cache_key(HOT_DASHBOARD_UID))
        _setup_done = True


class CacheBreakdownUser(HttpUser):
    """缓存击穿专项：先预热热点 key，再删 key 后并发回源。"""

    wait_time = between(0.1, 0.4)

    def on_start(self):
        _prepare_hot_key(self.client)

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
                response.failure(f'unexpected status={response.status_code}')
