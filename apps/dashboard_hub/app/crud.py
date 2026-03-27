from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cache
from app.ai_client import AIClient, AIClientError
from app.config import (
    AI_API_KEY,
    AI_ENABLED,
    AI_MAX_PANEL_JSON_CHARS,
    AI_MAX_PANELS_TO_SUMMARIZE,
    AI_MODEL,
    AI_PROMPT_VERSION,
    AI_PROVIDER,
    CACHE_TTL_SECONDS,
    GRAFANA_ADMIN_PASSWORD,
    GRAFANA_ADMIN_USER,
    GRAFANA_BASE_URL,
)
from app.metrics import CACHE_HIT_COUNT, CACHE_MISS_COUNT, SUMMARY_SOURCE_COUNT
from app.models import ShareLink, Subscription


def dashboard_exists(dashboard_uid: str) -> bool:
    response = requests.get(
        f"{GRAFANA_BASE_URL}/api/dashboards/uid/{dashboard_uid}",
        auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
        timeout=10,
    )
    return response.status_code == 200


def _flatten_panels(panels: list[dict] | None) -> list[dict]:
    if not panels:
        return []

    result: list[dict] = []
    for panel in panels:
        result.append(panel)
        nested = panel.get("panels")
        if nested:
            result.extend(_flatten_panels(nested))
    return result


def _extract_panel_titles(panels: list[dict] | None) -> list[str]:
    flat_panels = _flatten_panels(panels)

    titles: list[str] = []
    seen: set[str] = set()
    for panel in flat_panels:
        title = panel.get("title")
        if title and title not in seen:
            seen.add(title)
            titles.append(title)
    return titles


def _serialize_panel_for_ai(panel: dict[str, Any]) -> str:
    panel_json = json.dumps(panel, ensure_ascii=False, separators=(",", ":"), default=str)
    return panel_json[:AI_MAX_PANEL_JSON_CHARS]


def _extract_panel_payloads(panels: list[dict] | None) -> list[dict[str, Any]]:
    flat_panels = _flatten_panels(panels)
    payloads: list[dict[str, Any]] = []

    for panel in flat_panels[:AI_MAX_PANELS_TO_SUMMARIZE]:
        payloads.append(
            {
                "title": panel.get("title", ""),
                "panel_json": _serialize_panel_for_ai(panel),
            }
        )

    return payloads


def fetch_dashboard_context(dashboard_uid: str) -> dict | None:
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
    raw_panels = dashboard.get("panels", [])

    return {
        "dashboard_uid": dashboard_uid,
        "title": dashboard.get("title", ""),
        "url": meta.get("url"),
        "tags": dashboard.get("tags", []),
        "panels": _extract_panel_titles(raw_panels),
        "panel_payloads": _extract_panel_payloads(raw_panels),
    }


def build_fallback_summary(title: str, panels: list[str]) -> str:
    safe_title = title or "未命名 dashboard"
    if panels:
        focus = "、".join(panels[:3])
        return f"{safe_title}，主要关注{focus}。"
    return f"{safe_title}，用于展示相关监控信息。"


def _summary_cache_key(dashboard_uid: str) -> str:
    return f"dashhub:summary:{dashboard_uid}:{AI_PROVIDER}:{AI_MODEL}:{AI_PROMPT_VERSION}"


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


def _parse_expire_at(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="subscriptions").inc()
        return cached

    CACHE_MISS_COUNT.labels(cache_name="subscriptions").inc()

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
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="share_link").inc()
        expire_at = _parse_expire_at(cached.get("expire_at"))
        if _is_expired(expire_at):
            cache.delete(cache_key)
            return "expired"

        updated_rows = (
            db.query(ShareLink)
            .filter(ShareLink.token == token)
            .update({ShareLink.view_count: ShareLink.view_count + 1}, synchronize_session=False)
        )
        db.commit()
        if updated_rows == 0:
            cache.delete(cache_key)
            return None

        cached["view_count"] = int(cached.get("view_count", 0)) + 1
        cache.set_json(cache_key, cached, ex=CACHE_TTL_SECONDS)
        return cached

    CACHE_MISS_COUNT.labels(cache_name="share_link").inc()

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
    cache_key = _summary_cache_key(dashboard_uid)
    cached = cache.get_json(cache_key)
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="summary").inc()
        SUMMARY_SOURCE_COUNT.labels(source=cached.get("source", "fallback")).inc()
        return cached

    CACHE_MISS_COUNT.labels(cache_name="summary").inc()

    context = fetch_dashboard_context(dashboard_uid)
    if not context:
        return None

    payload = {
        "dashboard_uid": context["dashboard_uid"],
        "title": context["title"],
        "url": context["url"],
        "ai_summary": build_fallback_summary(context["title"], context["panels"]),
        "provider": AI_PROVIDER,
        "model": AI_MODEL,
        "prompt_version": AI_PROMPT_VERSION,
        "source": "fallback",
    }

    if AI_ENABLED and AI_API_KEY:
        try:
            ai_result = AIClient().summarize_dashboard(
                title=context["title"],
                tags=context["tags"],
                panel_titles=context["panels"],
                panel_payloads=context["panel_payloads"],
            )
            payload["ai_summary"] = ai_result["ai_summary"]
            payload["provider"] = ai_result["provider"]
            payload["model"] = ai_result["model"]
            payload["prompt_version"] = ai_result["prompt_version"]
            payload["source"] = "ai"
        except AIClientError:
            pass

    SUMMARY_SOURCE_COUNT.labels(source=payload["source"]).inc()
    cache.set_json(cache_key, payload, ex=CACHE_TTL_SECONDS)
    return payload
