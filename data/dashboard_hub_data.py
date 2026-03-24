from __future__ import annotations

from datetime import datetime, timedelta, timezone


def make_subscription_payload(dashboard_uid: str, user_login: str, channel: str = "email", cron: str = "0 */6 * * *") -> dict:
    return {
        "dashboard_uid": dashboard_uid,
        "user_login": user_login,
        "channel": channel,
        "cron": cron,
    }


def make_share_link_payload(dashboard_uid: str, ttl_hours: int = 24) -> dict:
    expire_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()
    return {
        "dashboard_uid": dashboard_uid,
        "expire_at": expire_at,
    }
