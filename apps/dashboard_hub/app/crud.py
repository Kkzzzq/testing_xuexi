from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import cache
from app.agent_log import record_event
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
    demo_fault_enabled,
)
from app.metrics import CACHE_HIT_COUNT, CACHE_MISS_COUNT, SUMMARY_SOURCE_COUNT
from app.models import ShareLink, Subscription


def dashboard_exists(dashboard_uid: str) -> bool:
    record_event("dashboard_lookup_started", dashboard_uid=dashboard_uid)
    response = requests.get(
        f"{GRAFANA_BASE_URL}/api/dashboards/uid/{dashboard_uid}",
        auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
        timeout=10,
    )
    exists = response.status_code == 200
    record_event(
        "dashboard_lookup_finished",
        dashboard_uid=dashboard_uid,
        status_code=response.status_code,
        exists=exists,
    )
    return exists


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
    record_event("summary_dashboard_context_fetch_started", dashboard_uid=dashboard_uid)
    response = requests.get(
        f"{GRAFANA_BASE_URL}/api/dashboards/uid/{dashboard_uid}",
        auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
        timeout=10,
    )
    if response.status_code != 200:
        record_event(
            "summary_dashboard_context_fetch_failed",
            dashboard_uid=dashboard_uid,
            status_code=response.status_code,
        )
        return None

    payload = response.json()
    meta = payload.get("meta", {})
    dashboard = payload.get("dashboard", {})
    raw_panels = dashboard.get("panels", [])
    record_event(
        "summary_dashboard_context_fetch_finished",
        dashboard_uid=dashboard_uid,
        panel_count=len(_flatten_panels(raw_panels)),
        tag_count=len(dashboard.get("tags", [])),
    )
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
    record_event(
        "subscription_create_started",
        dashboard_uid=dashboard_uid,
        user_login=user_login,
        channel=channel,
        cron=cron,
    )
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
        record_event(
            "subscription_create_integrity_error",
            dashboard_uid=dashboard_uid,
            user_login=user_login,
            channel=channel,
        )
        raise
    db.refresh(subscription)
    cache_key = f"dashhub:subscriptions:{dashboard_uid}"
    cache.delete(cache_key)
    record_event(
        "subscription_create_finished",
        dashboard_uid=dashboard_uid,
        user_login=user_login,
        channel=channel,
        subscription_id=subscription.id,
        cache_key=cache_key,
        cache_invalidated=True,
    )
    return subscription


def list_subscriptions(db: Session, dashboard_uid: str):
    cache_key = f"dashhub:subscriptions:{dashboard_uid}"
    record_event("subscription_list_started", dashboard_uid=dashboard_uid, cache_key=cache_key)
    cached = cache.get_json(cache_key)
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="subscriptions").inc()
        record_event(
            "subscription_list_cache_hit",
            dashboard_uid=dashboard_uid,
            cache_key=cache_key,
            item_count=len(cached.get("items", [])),
        )
        return cached

    CACHE_MISS_COUNT.labels(cache_name="subscriptions").inc()
    record_event("subscription_list_cache_miss", dashboard_uid=dashboard_uid, cache_key=cache_key)

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
    record_event(
        "subscription_list_cache_populated",
        dashboard_uid=dashboard_uid,
        cache_key=cache_key,
        item_count=len(payload["items"]),
    )
    return payload


def delete_subscription(db: Session, subscription_id: int):
    record_event("subscription_delete_started", subscription_id=subscription_id)
    row = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not row:
        record_event("subscription_delete_not_found", subscription_id=subscription_id)
        return None

    dashboard_uid = row.dashboard_uid
    cache_key = f"dashhub:subscriptions:{dashboard_uid}"
    db.delete(row)
    db.commit()
    record_event(
        "subscription_delete_db_committed",
        subscription_id=subscription_id,
        dashboard_uid=dashboard_uid,
    )

    if not demo_fault_enabled("subscription_cache_bug"):
        cache.delete(cache_key)
        record_event(
            "subscription_delete_cache_invalidated",
            subscription_id=subscription_id,
            dashboard_uid=dashboard_uid,
            cache_key=cache_key,
        )

    return row


def create_share_link(db: Session, dashboard_uid: str, expire_at: datetime | None):
    token = secrets.token_urlsafe(12)
    record_event(
        "share_link_create_started",
        dashboard_uid=dashboard_uid,
        token=token,
        expire_at=expire_at.isoformat() if expire_at else None,
    )
    share_link = ShareLink(
        dashboard_uid=dashboard_uid,
        token=token,
        expire_at=expire_at,
    )
    db.add(share_link)
    db.commit()
    db.refresh(share_link)
    cache_key = f"dashhub:share:{token}"
    cache.set_json(cache_key, _share_link_payload(share_link), ex=CACHE_TTL_SECONDS)
    record_event(
        "share_link_create_finished",
        dashboard_uid=dashboard_uid,
        token=token,
        cache_key=cache_key,
    )
    return share_link


def get_share_link(db: Session, token: str):
    cache_key = f"dashhub:share:{token}"
    record_event("share_link_read_started", token=token, cache_key=cache_key)
    cached = cache.get_json(cache_key)
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="share_link").inc()
        record_event("share_link_cache_hit", token=token, cache_key=cache_key)
        expire_at = _parse_expire_at(cached.get("expire_at"))
        if _is_expired(expire_at):
            cache.delete(cache_key)
            record_event("share_link_cache_entry_expired", token=token, cache_key=cache_key)
            return "expired"

        updated_rows = (
            db.query(ShareLink)
            .filter(ShareLink.token == token)
            .update({ShareLink.view_count: ShareLink.view_count + 1}, synchronize_session=False)
        )
        db.commit()
        if updated_rows == 0:
            cache.delete(cache_key)
            record_event("share_link_db_row_missing_after_cache_hit", token=token, cache_key=cache_key)
            return None

        cached["view_count"] = int(cached.get("view_count", 0)) + 1
        cache.set_json(cache_key, cached, ex=CACHE_TTL_SECONDS)
        record_event(
            "share_link_cache_refreshed_after_read",
            token=token,
            cache_key=cache_key,
            view_count=cached["view_count"],
        )
        return cached

    CACHE_MISS_COUNT.labels(cache_name="share_link").inc()
    record_event("share_link_cache_miss", token=token, cache_key=cache_key)

    row = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not row:
        cache.delete(cache_key)
        record_event("share_link_not_found", token=token, cache_key=cache_key)
        return None
    if _is_expired(row.expire_at):
        cache.delete(cache_key)
        record_event("share_link_expired", token=token, cache_key=cache_key)
        return "expired"

    row.view_count += 1
    db.commit()
    db.refresh(row)
    payload = _share_link_payload(row)
    cache.set_json(cache_key, payload, ex=CACHE_TTL_SECONDS)
    record_event(
        "share_link_read_finished",
        token=token,
        cache_key=cache_key,
        view_count=row.view_count,
    )
    return payload


def delete_share_link(db: Session, token: str):
    record_event("share_link_delete_started", token=token)
    row = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not row:
        record_event("share_link_delete_not_found", token=token)
        return None
    db.delete(row)
    db.commit()
    cache_key = f"dashhub:share:{token}"
    if not demo_fault_enabled("share_link_cache_bug"):
        cache.delete(cache_key)
        record_event("share_link_delete_cache_invalidated", token=token, cache_key=cache_key)
    record_event("share_link_delete_finished", token=token, cache_key=cache_key)
    return row


def get_dashboard_summary(dashboard_uid: str):
    cache_key = _summary_cache_key(dashboard_uid)
    record_event("summary_read_started", dashboard_uid=dashboard_uid, cache_key=cache_key)
    cached = cache.get_json(cache_key)
    if cached is not None:
        CACHE_HIT_COUNT.labels(cache_name="summary").inc()
        SUMMARY_SOURCE_COUNT.labels(source=cached.get("source", "fallback")).inc()
        record_event(
            "summary_cache_hit",
            dashboard_uid=dashboard_uid,
            cache_key=cache_key,
            source=cached.get("source", "fallback"),
        )
        return cached

    CACHE_MISS_COUNT.labels(cache_name="summary").inc()
    record_event("summary_cache_miss", dashboard_uid=dashboard_uid, cache_key=cache_key)

    context = fetch_dashboard_context(dashboard_uid)
    if not context:
        record_event("summary_dashboard_context_missing", dashboard_uid=dashboard_uid)
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
            record_event(
                "summary_ai_request_started",
                dashboard_uid=dashboard_uid,
                provider=AI_PROVIDER,
                model=AI_MODEL,
                panel_count=len(context["panel_payloads"]),
            )
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
            record_event(
                "summary_ai_request_finished",
                dashboard_uid=dashboard_uid,
                provider=payload["provider"],
                model=payload["model"],
                prompt_version=payload["prompt_version"],
            )
        except AIClientError as exc:
            record_event(
                "summary_ai_request_failed",
                dashboard_uid=dashboard_uid,
                error=str(exc),
            )

    SUMMARY_SOURCE_COUNT.labels(source=payload["source"]).inc()
    cache.set_json(cache_key, payload, ex=CACHE_TTL_SECONDS)
    record_event(
        "summary_cache_populated",
        dashboard_uid=dashboard_uid,
        cache_key=cache_key,
        source=payload["source"],
    )
    return payload
