from __future__ import annotations

import secrets
from datetime import datetime, timezone

import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cache
from app.config import CACHE_TTL_SECONDS, GRAFANA_ADMIN_PASSWORD, GRAFANA_ADMIN_USER, GRAFANA_BASE_URL
from app.models import ShareLink, Subscription


def dashboard_exists(dashboard_uid: str) -> bool:
    response = requests.get(
        f"{GRAFANA_BASE_URL}/api/dashboards/uid/{dashboard_uid}",
        auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
        timeout=10,
    )
    return response.status_code == 200


def fetch_dashboard_summary(dashboard_uid: str) -> dict | None:
    response = requests.get(
        f"{GRAFANA_BASE_URL}/api/dashboards/uid/{dashboard_uid}",
        auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
        timeout=10,
    )
    if response.status_code != 200:
        return None

    payload = response.json()
    meta = payload.get("meta", {})
    dashboard = payload.get("dashboard", {})
    return {
        "dashboard_uid": dashboard_uid,
        "title": dashboard.get("title", ""),
        "url": meta.get("url"),
    }


def _share_link_payload(row: ShareLink) -> dict:
    return {
        "id": row.id,
        "dashboard_uid": row.dashboard_uid,
        "token": row.token,
        "expire_at": row.expire_at.isoformat() if row.expire_at else None,
        "view_count": row.view_count,
        "created_at": row.created_at.isoformat(),
    }


def _is_expired(expire_at: datetime | None) -> bool:
    if expire_at is None:
        return False
    if expire_at.tzinfo is None:
        expire_at = expire_at.replace(tzinfo=timezone.utc)
    return expire_at < datetime.now(timezone.utc)


def create_subscription(db: Session, dashboard_uid: str, user_login: str, channel: str, cron: str):
    subscription = Subscription(
        dashboard_uid=dashboard_uid,
        user_login=user_login,
        channel=channel,
        cron=cron,
    )
    db.add(subscription)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(subscription)
    cache.delete(f"dashhub:subscriptions:{dashboard_uid}")
    return subscription


def list_subscriptions(db: Session, dashboard_uid: str):
    cache_key = f"dashhub:subscriptions:{dashboard_uid}"
    cached = cache.get_json(cache_key)
    if cached:
        return cached

    rows = (
        db.query(Subscription)
        .filter(Subscription.dashboard_uid == dashboard_uid)
        .order_by(Subscription.id.desc())
        .all()
    )
    payload = {
        "dashboard_uid": dashboard_uid,
        "items": [
            {
                "id": row.id,
                "dashboard_uid": row.dashboard_uid,
                "user_login": row.user_login,
                "channel": row.channel,
                "cron": row.cron,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }
    cache.set_json(cache_key, payload, ex=CACHE_TTL_SECONDS)
    return payload


def delete_subscription(db: Session, subscription_id: int):
    row = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not row:
        return None
    dashboard_uid = row.dashboard_uid
    db.delete(row)
    db.commit()
    cache.delete(f"dashhub:subscriptions:{dashboard_uid}")
    return row


def create_share_link(db: Session, dashboard_uid: str, expire_at: datetime | None):
    token = secrets.token_urlsafe(12)
    share_link = ShareLink(
        dashboard_uid=dashboard_uid,
        token=token,
        expire_at=expire_at,
    )
    db.add(share_link)
    db.commit()
    db.refresh(share_link)
    cache.set_json(
        f"dashhub:share:{token}",
        _share_link_payload(share_link),
        ex=CACHE_TTL_SECONDS,
    )
    return share_link


def get_share_link(db: Session, token: str):
    cache_key = f"dashhub:share:{token}"
    cached = cache.get_json(cache_key)

    row = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not row:
        cache.delete(cache_key)
        return None

    if _is_expired(row.expire_at):
        cache.delete(cache_key)
        return "expired"

    row.view_count += 1
    db.commit()
    db.refresh(row)

    payload = _share_link_payload(row)
    cache.set_json(cache_key, payload, ex=CACHE_TTL_SECONDS)

    return payload


def delete_share_link(db: Session, token: str):
    row = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not row:
        return None
    db.delete(row)
    db.commit()
    cache.delete(f"dashhub:share:{token}")
    return row


def get_dashboard_summary(dashboard_uid: str):
    cache_key = f"dashhub:summary:{dashboard_uid}"
    cached = cache.get_json(cache_key)
    if cached:
        return cached

    payload = fetch_dashboard_summary(dashboard_uid)
    if not payload:
        return None

    cache.set_json(cache_key, payload, ex=CACHE_TTL_SECONDS)
    return payload
