from __future__ import annotations

import os
from itertools import count, cycle

from locust import HttpUser, between, task


def _split_env(name: str) -> list[str]:
    raw = os.getenv(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, '') else default


DASHBOARD_UIDS = _split_env('LOCUST_DASHBOARD_UIDS')
CONFLICT_USER_LOGIN = os.getenv('LOCUST_CONFLICT_USER_LOGIN', 'locust_conflict_user')
CONFLICT_DASHBOARD_UID = (
    os.getenv('LOCUST_CONFLICT_DASHBOARD_UID')
    or os.getenv('LOCUST_HOT_DASHBOARD_UID')
    or (DASHBOARD_UIDS[0] if DASHBOARD_UIDS else '')
).strip()
_CHANNELS = ('email', 'slack', 'webhook')
WAIT_MIN_SECONDS = _env_float('LOCUST_WAIT_MIN_SECONDS', 0.01)
WAIT_MAX_SECONDS = _env_float('LOCUST_WAIT_MAX_SECONDS', 0.04)

_dashboard_cycle = cycle(DASHBOARD_UIDS) if DASHBOARD_UIDS else None
_login_counter = count(1)
_channel_counter = count(0)


def _next_dashboard_uid() -> str | None:
    if _dashboard_cycle is None:
        return None
    return next(_dashboard_cycle)


def _next_user_login() -> str:
    return f'locust_writer_{next(_login_counter)}'


def _next_channel() -> str:
    return _CHANNELS[next(_channel_counter) % len(_CHANNELS)]


class WriteConflictUser(HttpUser):
    """写入与冲突场景：更接近高并发写压力，而不是轻量功能压测。"""

    wait_time = between(WAIT_MIN_SECONDS, WAIT_MAX_SECONDS)

    @task(2)
    def create_subscription_normal(self):
        dashboard_uid = _next_dashboard_uid()
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

    @task(3)
    def create_subscription_conflict(self):
        dashboard_uid = CONFLICT_DASHBOARD_UID
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
            if response.status_code == 409:
                response.success()
            else:
                response.failure(
                    f'expected 409 conflict, got status={response.status_code}, body={response.text[:200]}'
                )
